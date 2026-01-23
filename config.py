"""Configuration management for the application."""
import os


class Config:
    """Application configuration."""

    def __init__(self):
        self.project_id = os.environ.get('GCP_PROJECT_ID')
        self.spreadsheet_id = os.environ.get('SPREADSHEET_ID')
        self.drive_parent_folder_id = os.environ.get('DRIVE_PARENT_FOLDER_ID')
        self.firestore_collection = os.environ.get('FIRESTORE_COLLECTION', 'processed_domains')
        self.vertex_ai_region = os.environ.get('VERTEX_AI_REGION', 'us-central1')
        self.linkedin_cookie = os.environ.get('LINKEDIN_COOKIE', '')
        self.bookface_cookie = os.environ.get('BOOKFACE_COOKIE', '')
        self.serper_api_key = os.environ.get('SERPER_API_KEY', '')

        self.validate()

    def validate(self):
        """Validate required configuration."""
        required = {
            'GCP_PROJECT_ID': self.project_id,
            'SPREADSHEET_ID': self.spreadsheet_id,
            'DRIVE_PARENT_FOLDER_ID': self.drive_parent_folder_id,
        }

        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")


# Global config instance
config = Config()
