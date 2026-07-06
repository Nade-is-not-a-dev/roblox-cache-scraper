"""Formatting helper utilities."""


def format_count(count: int, noun: str) -> str:
    """Format a count with proper pluralization."""
    if count == 1:
        return f'{count} {noun}'
    return f'{count} {noun}s'


def format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f'{size_bytes:.1f} {unit}' if isinstance(size_bytes, float) else f'{size_bytes} {unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f} TB'
