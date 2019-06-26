from dataclasses import dataclass, Field, fields, field, asdict
from typing import TypeVar, Generic, Type, Any, Optional, Iterator

from google.cloud import firestore
from google.cloud.firestore_v1 import CollectionReference, Query, Transaction
from google.cloud.firestore_v1.proto.write_pb2 import WriteResult
from google.protobuf.timestamp_pb2 import Timestamp
from typing_extensions import Literal


_firestore_client: Optional[firestore.Client] = None


def initialize_firestore(db: firestore.Client) -> None:
    global _firestore_client
    _firestore_client = db


class NotInitialized(Exception):
    pass


def _get_firestore_client() -> firestore.Client:
    if _firestore_client is None:
        raise NotInitialized()
    return _firestore_client


_DocumentClsTypeVar = TypeVar('_DocumentClsTypeVar', bound="Document")


class DocumentQuery:

    def __init__(self, document_cls: Type[_DocumentClsTypeVar], firestore_query: Query) -> None:
        self._document_cls = document_cls
        self._firestore_query = firestore_query

    def limit(self, count: int) -> 'DocumentQuery':
        new_query = self._firestore_query.limit(count)
        return DocumentQuery(self._document_cls, new_query)

    def get(self, transaction: Optional[Transaction] = None) -> Iterator[_DocumentClsTypeVar]:
        for firestore_document in self._firestore_query.get(transaction):
            document = self._document_cls(**firestore_document.to_dict())
            document._id = firestore_document.id
            yield document


FirestoreOperator = Literal["<", "<=", "==", ">=", ">", "array_contains"]


class DocumentNotFound(Exception):
    pass


class DocumentNotSavedToDatabase(Exception):
    pass


class DocumentAlreadyExistsInDatabase(Exception):
    pass


_DocumentTypeVar = TypeVar('_DocumentTypeVar', bound="Document")


@dataclass
class Document:

    def __post_init__(self) -> None:
        self._id: Optional[str] = None  # Set when the document was saved to the DB or retrieved from the DB

    @property
    def id(self) -> Optional[str]:
        return self._id

    def create(self, document_id: Optional[str] = None) -> WriteResult:
        if self.id is not None:
            raise DocumentAlreadyExistsInDatabase()
        document_ref = self._collection().document(document_id)
        write_result = document_ref.create(asdict(self))
        self._id = document_ref.id
        return write_result

    def update(self) -> WriteResult:
        if self.id is None:
            raise DocumentNotSavedToDatabase()
        document_ref = self._collection().document(self.id)
        write_result = document_ref.update(asdict(self))
        self._id = document_ref.id
        return write_result

    def delete(self) -> Timestamp:
        if self.id is None:
            raise DocumentNotSavedToDatabase()
        return self.delete_document(self.id)

    @classmethod
    def _collection(cls: Type[_DocumentTypeVar]) -> CollectionReference:
        return _get_firestore_client().collection(cls.__name__)

    @classmethod
    def get_document(cls: Type[_DocumentTypeVar], document_id: str) -> _DocumentTypeVar:
        firestore_document = cls._collection().document(document_id).get()
        if not firestore_document or not firestore_document.exists:
            raise DocumentNotFound()
        document = cls(**firestore_document.to_dict())
        document._id = firestore_document.id
        return document

    @classmethod
    def delete_document(cls: Type[_DocumentTypeVar], document_id: str) -> Timestamp:
        return cls._collection().document(document_id).delete()

    @classmethod
    def get(cls: Type[_DocumentTypeVar]) -> Iterator[_DocumentTypeVar]:
        for firestore_document in cls._collection().get():
            document = cls(**firestore_document.to_dict())
            document._id = firestore_document.id
            yield document

    @classmethod
    def where(
            cls: Type[_DocumentTypeVar],
            field_path: str,
            op_string: FirestoreOperator,
            value: Any
    ) -> DocumentQuery:
        # TODO: Add support for .
        # Check that the field exists
        corresponding_field = None
        for defined_field in fields(cls):
            if defined_field.name == field_path:
                corresponding_field = defined_field

        if not corresponding_field:
            raise TypeError()

        # Check that the value has the right type
        if corresponding_field.type != type(value):
            raise TypeError()

        return DocumentQuery(cls, cls.collection().where(field_path, op_string, value))