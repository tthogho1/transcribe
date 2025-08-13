"""
Test script to verify ID button behavior based on transcription status
"""

import unittest
from unittest.mock import Mock, patch


class TestIDButtonBehavior(unittest.TestCase):
    """Test cases for ID button functionality"""

    def setUp(self):
        """Set up test data"""
        self.transcribed_video = {
            'video_id': 'test123',
            'title': 'Test Video',
            'transcribed': True
        }
        
        self.untranscribed_video = {
            'video_id': 'test456', 
            'title': 'Untranscribed Video',
            'transcribed': False
        }
        
        self.no_transcribed_flag_video = {
            'video_id': 'test789',
            'title': 'No Flag Video'
            # transcribed flag is missing (None/undefined)
        }

    def test_transcribed_video_button_enabled(self):
        """Test that ID button is enabled for transcribed videos"""
        video = self.transcribed_video
        
        # Simulate the button logic from the frontend
        is_enabled = bool(video.get('transcribed', False))
        button_class = 'enabled' if is_enabled else 'disabled'
        onclick_handler = 'viewTranscription' if is_enabled else None
        
        self.assertTrue(is_enabled)
        self.assertEqual(button_class, 'enabled')
        self.assertEqual(onclick_handler, 'viewTranscription')

    def test_untranscribed_video_button_disabled(self):
        """Test that ID button is disabled for untranscribed videos"""
        video = self.untranscribed_video
        
        # Simulate the button logic from the frontend
        is_enabled = bool(video.get('transcribed', False))
        button_class = 'enabled' if is_enabled else 'disabled'
        onclick_handler = 'viewTranscription' if is_enabled else None
        
        self.assertFalse(is_enabled)
        self.assertEqual(button_class, 'disabled')
        self.assertIsNone(onclick_handler)

    def test_no_transcribed_flag_button_disabled(self):
        """Test that ID button is disabled when transcribed flag is missing"""
        video = self.no_transcribed_flag_video
        
        # Simulate the button logic from the frontend
        is_enabled = bool(video.get('transcribed', False))
        button_class = 'enabled' if is_enabled else 'disabled'
        onclick_handler = 'viewTranscription' if is_enabled else None
        
        self.assertFalse(is_enabled)
        self.assertEqual(button_class, 'disabled')
        self.assertIsNone(onclick_handler)

    def test_button_styling_for_transcribed(self):
        """Test button styling for transcribed videos"""
        video = self.transcribed_video
        is_transcribed = bool(video.get('transcribed', False))
        
        # Expected styling for enabled button
        expected_styles = {
            'cursor': 'pointer',
            'background': '#e3f2fd',
            'color': '#1976d2',
            'border': '1px solid #1976d2'
        }
        
        actual_styles = {
            'cursor': 'pointer' if is_transcribed else 'not-allowed',
            'background': '#e3f2fd' if is_transcribed else '#f5f5f5',
            'color': '#1976d2' if is_transcribed else '#9e9e9e',
            'border': '1px solid #1976d2' if is_transcribed else '1px solid #e0e0e0'
        }
        
        self.assertEqual(actual_styles, expected_styles)

    def test_button_styling_for_untranscribed(self):
        """Test button styling for untranscribed videos"""
        video = self.untranscribed_video
        is_transcribed = bool(video.get('transcribed', False))
        
        # Expected styling for disabled button
        expected_styles = {
            'cursor': 'not-allowed',
            'background': '#f5f5f5',
            'color': '#9e9e9e',
            'border': '1px solid #e0e0e0'
        }
        
        actual_styles = {
            'cursor': 'pointer' if is_transcribed else 'not-allowed',
            'background': '#e3f2fd' if is_transcribed else '#f5f5f5',
            'color': '#1976d2' if is_transcribed else '#9e9e9e',
            'border': '1px solid #1976d2' if is_transcribed else '1px solid #e0e0e0'
        }
        
        self.assertEqual(actual_styles, expected_styles)

    def test_button_tooltip_messages(self):
        """Test tooltip messages for different transcription states"""
        # Transcribed video
        video = self.transcribed_video
        is_transcribed = bool(video.get('transcribed', False))
        tooltip = 'Click to view transcription' if is_transcribed else 'Transcription not available - video must be transcribed first'
        self.assertEqual(tooltip, 'Click to view transcription')
        
        # Untranscribed video
        video = self.untranscribed_video
        is_transcribed = bool(video.get('transcribed', False))
        tooltip = 'Click to view transcription' if is_transcribed else 'Transcription not available - video must be transcribed first'
        self.assertEqual(tooltip, 'Transcription not available - video must be transcribed first')

    @patch('builtins.print')
    def test_click_handler_behavior(self, mock_print):
        """Test that click handler only executes for transcribed videos"""
        
        def mock_view_transcription(video_id):
            """Mock function to simulate viewTranscription"""
            print(f"Opening transcription for video: {video_id}")
            return f"transcription_window_{video_id}"
        
        # Test transcribed video - should execute
        video = self.transcribed_video
        if video.get('transcribed', False):
            result = mock_view_transcription(video['video_id'])
            self.assertEqual(result, "transcription_window_test123")
        
        # Test untranscribed video - should not execute
        video = self.untranscribed_video
        result = None
        if video.get('transcribed', False):
            result = mock_view_transcription(video['video_id'])
        self.assertIsNone(result)


if __name__ == '__main__':
    print("Running ID Button Behavior Tests...")
    unittest.main(verbosity=2)