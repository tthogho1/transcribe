"""
YouTube Video DynamoDB Client
Handles interactions with DynamoDB for YouTube video data management
"""

import boto3
import logging
import re
import unicodedata
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError


@dataclass
class VideoRecord:
    """Data class representing a YouTube video record"""

    video_id: str
    title: str
    author: str
    duration: str
    views: int
    description: str
    url: str
    transcribed: bool
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "video_id": self.video_id,
            "title": self.title,
            "author": self.author,
            "duration": self.duration,
            "views": self.views,
            "description": self.description,
            "url": self.url,
            "transcribed": self.transcribed,
            "created_at": (
                self.created_at.isoformat()
                if isinstance(self.created_at, datetime)
                else self.created_at
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if isinstance(self.updated_at, datetime)
                else self.updated_at
            ),
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "VideoRecord":
        """Create VideoRecord from DynamoDB item"""

        # Helper function to parse datetime from string or return datetime object
        def parse_datetime(value):
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    return datetime.now()
            elif isinstance(value, datetime):
                return value
            else:
                return datetime.now()

        return cls(
            video_id=item.get("video_id", ""),
            title=item.get("title", ""),
            author=item.get("author", ""),
            duration=item.get("duration", ""),
            views=int(item.get("views", 0)),
            description=item.get("description", ""),
            url=item.get("url", ""),
            transcribed=bool(
                int(item.get("transcribed", 0))
            ),  # Convert number to boolean
            created_at=parse_datetime(item.get("created_at", datetime.now())),
            updated_at=parse_datetime(item.get("updated_at", datetime.now())),
        )


class YouTubeDynamoDBClient:
    """DynamoDB client for YouTube video data management"""

    def __init__(self, table_name: str):
        """Initialize DynamoDB client"""
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def normalize_text_for_search(text: str) -> str:
        """
        Normalize text for search by:
        1. Converting to lowercase
        2. Converting hiragana to katakana
        3. Normalizing unicode
        4. Removing extra whitespace
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Normalize unicode
        text = unicodedata.normalize("NFKC", text)

        # Convert hiragana to katakana
        normalized = ""
        for char in text:
            # Hiragana range: U+3040-U+309F
            # Katakana range: U+30A0-U+30FF
            code = ord(char)
            if 0x3040 <= code <= 0x309F:
                # Convert hiragana to katakana
                normalized += chr(code + 0x60)
            else:
                normalized += char

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _text_contains_normalized(self, haystack: str, needle: str) -> bool:
        """Check if haystack contains needle using normalized text comparison"""
        if not needle or not haystack:
            return False

        normalized_haystack = self.normalize_text_for_search(haystack)
        normalized_needle = self.normalize_text_for_search(needle)

        return normalized_needle in normalized_haystack

    def test_connection(self) -> bool:
        """Test DynamoDB connection"""
        try:
            self.table.table_status
            return True
        except Exception as e:
            self.logger.error(f"DynamoDB connection failed: {e}")
            return False

    def get_videos(
        self,
        limit: int = 50,
        last_evaluated_key: Optional[Dict] = None,
        transcribed_filter: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Get videos with pagination and optional transcribed filter"""
        try:
            scan_kwargs = {"Limit": limit}
            if last_evaluated_key:
                scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

            # Add transcribed filter if specified
            if transcribed_filter is not None:
                scan_kwargs["FilterExpression"] = Attr("transcribed").eq(
                    transcribed_filter
                )

            response = self.table.scan(**scan_kwargs)

            videos = [
                VideoRecord.from_dynamodb_item(item).to_dict()
                for item in response.get("Items", [])
            ]

            return {
                "videos": videos,
                "last_evaluated_key": response.get("LastEvaluatedKey"),
                "count": len(videos),
            }

        except ClientError as e:
            self.logger.error(f"Error getting videos: {e}")
            return {"videos": [], "last_evaluated_key": None, "count": 0}

    def search_videos(
        self,
        search_term: str,
        limit: int = 50,
        last_evaluated_key: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Search videos by title, author, or description with Japanese text normalization"""
        try:
            if not search_term:
                return self.get_videos(limit, last_evaluated_key)

            # First, try DynamoDB scan with contains for basic filtering
            scan_kwargs = {
                "Limit": limit * 3,  # Get more items to filter locally
                "FilterExpression": (
                    Attr("title").contains(search_term)
                    | Attr("author").contains(search_term)
                    | Attr("description").contains(search_term)
                ),
            }

            if last_evaluated_key:
                scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

            response = self.table.scan(**scan_kwargs)

            # Also do a broader scan for Japanese text normalization
            all_items = []

            # First add items that matched DynamoDB contains
            all_items.extend(response.get("Items", []))

            # Then scan more broadly for normalized matching
            broad_scan_kwargs = {"Limit": limit * 5}  # Cast wider net
            if last_evaluated_key:
                broad_scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

            broad_response = self.table.scan(**broad_scan_kwargs)

            # Filter items using normalized text matching
            normalized_matches = []
            for item in broad_response.get("Items", []):
                # Check if any field contains the search term (normalized)
                title = item.get("title", "")
                author = item.get("author", "")
                description = item.get("description", "")

                if (
                    self._text_contains_normalized(title, search_term)
                    or self._text_contains_normalized(author, search_term)
                    or self._text_contains_normalized(description, search_term)
                ):
                    normalized_matches.append(item)

            # Combine and deduplicate results
            seen_ids = set()
            combined_items = []

            for item in all_items + normalized_matches:
                video_id = item.get("video_id")
                if video_id and video_id not in seen_ids:
                    seen_ids.add(video_id)
                    combined_items.append(item)

            # Limit results
            limited_items = combined_items[:limit]

            videos = [
                VideoRecord.from_dynamodb_item(item).to_dict() for item in limited_items
            ]

            # Determine if there are more results
            has_more = len(combined_items) > limit
            next_key = response.get("LastEvaluatedKey") if has_more else None

            return {
                "videos": videos,
                "last_evaluated_key": next_key,
                "count": len(videos),
                "search_term": search_term,
            }

        except ClientError as e:
            self.logger.error(f"Error searching videos: {e}")
            return {
                "videos": [],
                "last_evaluated_key": None,
                "count": 0,
                "search_term": search_term,
            }

    def get_video_by_id(self, video_id: str) -> Optional[VideoRecord]:
        """Get a single video by ID"""
        try:
            response = self.table.get_item(Key={"video_id": video_id})
            item = response.get("Item")
            return VideoRecord.from_dynamodb_item(item) if item else None

        except ClientError as e:
            self.logger.error(f"Error getting video {video_id}: {e}")
            return None

    def create_video(self, video_data: Dict[str, Any]) -> Optional[VideoRecord]:
        """Create a new video record"""
        try:
            now = datetime.now().isoformat()
            video_data["created_at"] = now
            video_data["updated_at"] = now

            self.table.put_item(Item=video_data)
            return VideoRecord.from_dynamodb_item(video_data)

        except ClientError as e:
            self.logger.error(f"Error creating video: {e}")
            return None

    def update_video(
        self, video_id: str, update_data: Dict[str, Any]
    ) -> Optional[VideoRecord]:
        """Update an existing video record"""
        try:
            update_data["updated_at"] = datetime.now().isoformat()

            # Build update expression
            update_expression = "SET "
            expression_attribute_values = {}

            for key, value in update_data.items():
                # Convert datetime objects to ISO format strings for DynamoDB
                if isinstance(value, datetime):
                    value = value.isoformat()
                update_expression += f"#{key} = :{key}, "
                expression_attribute_values[f":{key}"] = value

            update_expression = update_expression.rstrip(", ")

            # Create attribute names mapping
            expression_attribute_names = {f"#{key}": key for key in update_data.keys()}

            response = self.table.update_item(
                Key={"video_id": video_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="ALL_NEW",
            )

            return VideoRecord.from_dynamodb_item(response["Attributes"])

        except ClientError as e:
            self.logger.error(f"Error updating video {video_id}: {e}")
            return None

    def update_transcribed_status(self, video_id: str, transcribed: bool) -> bool:
        """
        Update transcribed status for a video

        Args:
            video_id: ビデオID
            transcribed: transcribe状態 (True/False)

        Returns:
            更新成功時True、失敗時False
        """
        try:
            # Convert boolean to number for DynamoDB GSI compatibility (0 = false, 1 = true)
            transcribed_value = 1 if transcribed else 0
            result = self.update_video(video_id, {"transcribed": transcribed_value})
            if result:
                self.logger.debug(
                    f"Video {video_id} transcribed status updated to {transcribed}"
                )
                return True
            else:
                self.logger.warning(
                    f"Failed to update transcribed status for video {video_id}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Error updating transcribed status for {video_id}: {e}")
            return False

    def delete_video(self, video_id: str) -> bool:
        """Delete a video record"""
        try:
            self.table.delete_item(Key={"video_id": video_id})
            return True

        except ClientError as e:
            self.logger.error(f"Error deleting video {video_id}: {e}")
            return False

    def get_video_count(self) -> int:
        """Get total count of videos in the table"""
        try:
            response = self.table.scan(Select="COUNT")
            return response.get("Count", 0)

        except ClientError as e:
            self.logger.error(f"Error getting video count: {e}")
            return 0

    def get_videos_stats(self) -> Dict[str, int]:
        """Get statistics about videos in the table"""
        try:
            # Get total count
            total_response = self.table.scan(Select="COUNT")
            total_count = total_response.get("Count", 0)

            # Get transcribed count
            transcribed_response = self.table.scan(
                Select="COUNT", FilterExpression=Attr("transcribed").eq(True)
            )
            transcribed_count = transcribed_response.get("Count", 0)

            # Get not transcribed count
            not_transcribed_count = total_count - transcribed_count

            # Calculate transcription percentage
            transcription_percentage = (
                (transcribed_count / total_count * 100) if total_count > 0 else 0
            )

            return {
                "total": total_count,
                "transcribed": transcribed_count,
                "not_transcribed": not_transcribed_count,
                # Frontend expects these field names
                "total_videos": total_count,
                "transcribed_videos": transcribed_count,
                "untranscribed_videos": not_transcribed_count,
                "transcription_percentage": round(transcription_percentage, 1),
            }

        except ClientError as e:
            self.logger.error(f"Error getting video stats: {e}")
            return {
                "total": 0,
                "transcribed": 0,
                "not_transcribed": 0,
                "total_videos": 0,
                "transcribed_videos": 0,
                "untranscribed_videos": 0,
                "transcription_percentage": 0,
            }
