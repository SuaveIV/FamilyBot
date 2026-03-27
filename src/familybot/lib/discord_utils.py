"""Discord-specific utility functions for message formatting and splitting."""

from familybot.lib.logging_config import get_logger

logger = get_logger(__name__)


def split_message(message: str, max_length: int = 1900) -> list[str]:
    """
    Split a message into multiple parts that fit within Discord's character limit.

    Args:
        message: The message to split
        max_length: Maximum length per message part (default 1900 to stay well under 2000 limit)

    Returns:
        List of message parts
    """
    if len(message) <= max_length:
        return [message]

    parts = []
    current_part = ""

    # Split by lines first to preserve formatting
    lines = message.split("\n")

    for line in lines:
        # If a single line is too long, we need to split it
        if len(line) > max_length:
            # If we have content in current_part, save it first
            if current_part:
                parts.append(current_part.rstrip())
                current_part = ""

            # Split the long line by words
            words = line.split(" ")
            for word in words:
                # If adding this word would exceed limit, start new part
                if len(current_part) + len(word) + 1 > max_length:
                    if current_part:
                        parts.append(current_part.rstrip())
                        current_part = word + " "
                    else:
                        # Single word is too long, truncate it
                        parts.append(word[: max_length - 3] + "...")
                        current_part = ""
                else:
                    current_part += word + " "
        else:
            # Check if adding this line would exceed the limit
            if len(current_part) + len(line) + 1 > max_length:
                # Save current part and start new one
                if current_part:
                    parts.append(current_part.rstrip())
                current_part = line + "\n"
            else:
                current_part += line + "\n"

    # Add any remaining content
    if current_part:
        parts.append(current_part.rstrip())

    return parts


def truncate_message_list(
    items: list[str],
    header: str = "",
    footer_template: str = "\n... and {count} more items!",
    max_length: int = 1900,
) -> str:
    """
    Truncates a list of items to fit within Discord's message limit.

    Args:
        items: List of strings to include in the message
        header: Optional header text to prepend
        footer_template: Template for footer when truncation occurs. Use {count} for remaining items count.
        max_length: Maximum message length (defaults to Discord's limit)

    Returns:
        Formatted message string that fits within the character limit
    """
    if not items:
        return header

    # Build full content first
    full_content = header + "\n".join(items)

    # If it fits, return as-is
    if len(full_content) <= max_length:
        return full_content

    # Calculate available space for items
    sample_footer = footer_template.format(count=999)  # Use max digits for calculation
    available_space = max_length - len(header) - len(sample_footer)

    if available_space <= 0:
        logger.warning(
            f"Header and footer too long for message truncation. Header: {len(header)}, Footer: {len(sample_footer)}"
        )
        return header[:max_length]

    # Add items until we run out of space
    truncated_items = []
    current_length = 0

    for item in items:
        item_length = len(item) + 1  # +1 for newline
        if current_length + item_length > available_space:
            break
        truncated_items.append(item)
        current_length += item_length

    # Build final message
    if len(truncated_items) < len(items):
        remaining_count = len(items) - len(truncated_items)
        footer = footer_template.format(count=remaining_count)
        result = header + "\n".join(truncated_items) + footer
        logger.info(
            f"Message truncated: showing {len(truncated_items)} items, hiding {remaining_count} items"
        )
        return result
    else:
        return header + "\n".join(truncated_items)
