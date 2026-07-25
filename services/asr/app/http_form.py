"""Lecture d'une requête ``multipart/form-data`` — sans dépendance lourde.

Le service ASR local (`services/asr/local_server.py`) doit honorer **exactement**
le contrat que `RemoteCtcRecognizer` envoie déjà à Modal : un POST multipart avec
un fichier ``audio`` et des champs texte. L'analyse de cette requête n'a aucune
raison d'exiger FastAPI — et la garder ici, en stdlib pure, permet de la
**tester en CI** (sans torch, sans modèle, sans GPU) là où le serveur lui-même
ne peut pas l'être.

Volontairement minimal : ce module lit ce que le projet envoie, il ne prétend pas
couvrir tout le RFC 7578.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default as default_policy


class MultipartError(ValueError):
    """Requête multipart illisible — refus explicite, jamais un champ deviné."""


@dataclass(frozen=True)
class FormData:
    """Champs texte et fichiers d'une requête multipart."""

    fields: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)

    def require_file(self, name: str) -> bytes:
        try:
            return self.files[name]
        except KeyError as exc:
            raise MultipartError(f"fichier '{name}' absent de la requête") from exc


def parse_multipart(body: bytes, content_type: str) -> FormData:
    """Décompose ``body`` selon ``content_type``.

    :raises MultipartError: si l'en-tête n'annonce pas du multipart, si la
        frontière manque, ou si le corps n'est pas décomposable. On refuse au
        lieu d'inventer un champ vide — une requête mal formée doit se voir.
    """
    if "multipart/form-data" not in content_type.lower():
        raise MultipartError(f"content-type inattendu : {content_type!r}")
    if "boundary=" not in content_type.lower():
        raise MultipartError("frontière (boundary) absente du content-type")

    # `BytesParser` attend un message complet : on lui reconstitue l'en-tête.
    message = BytesParser(policy=default_policy).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
    )
    if not message.is_multipart():
        raise MultipartError("corps de requête non multipart")

    fields: dict[str, str] = {}
    files: dict[str, bytes] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str):
            continue
        payload = part.get_payload(decode=True) or b""
        if part.get_filename():
            files[name] = payload
        else:
            fields[name] = payload.decode("utf-8", errors="replace")
    return FormData(fields=fields, files=files)


__all__ = ["FormData", "MultipartError", "parse_multipart"]
