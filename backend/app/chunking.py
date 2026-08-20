"""Découpage des documents en chunks pour l'indexation vectorielle.

Utilise LangChain (`RecursiveCharacterTextSplitter`) avec un vrai tokenizer
(`tiktoken`) : la taille des chunks est mesurée en tokens, pas en
caractères, ce qui colle à la façon dont les LLM "voient" le texte.
"""
import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import Config

_encoding = tiktoken.get_encoding("cl100k_base")


def _token_length(text: str) -> int:
    return len(_encoding.encode(text))


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=Config.CHUNK_SIZE_TOKENS,
    chunk_overlap=Config.CHUNK_OVERLAP_TOKENS,
    length_function=_token_length,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_text(text: str) -> list[str]:
    """Découpe un texte en chunks d'environ `CHUNK_SIZE_TOKENS` tokens, avec recouvrement."""
    return _splitter.split_text(text)
