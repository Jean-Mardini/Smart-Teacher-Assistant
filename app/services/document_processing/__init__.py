"""
Document processing services (implemented by Matheos).
Handles document loading, parsing, structure extraction, and JSON generation.
"""

from .pipeline import process_document

__all__ = ["process_document"]