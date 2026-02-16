"""
Caption Manager: Templates, variables, hashtag pools, rotation.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default caption templates and hashtags directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CAPTIONS_DIR = PROJECT_ROOT / "captions"
CAPTIONS_TEMPLATES = CAPTIONS_DIR / "templates.json"
CAPTIONS_HASHTAGS = CAPTIONS_DIR / "hashtags.json"


class CaptionManager:
    """Manages captions and hashtags."""
    
    def __init__(self, templates_file: Optional[Path] = None, hashtags_file: Optional[Path] = None):
        self.templates_file = templates_file or CAPTIONS_TEMPLATES
        self.hashtags_file = hashtags_file or CAPTIONS_HASHTAGS
        self._ensure_files()
        self.templates: Dict[str, List[str]] = {}
        self.hashtag_pools: Dict[str, List[str]] = {}
        self._load_templates()
        self._load_hashtags()
    
    def _ensure_files(self):
        """Create default caption/hashtag files if they don't exist."""
        self.templates_file.parent.mkdir(parents=True, exist_ok=True)
        
        if not self.templates_file.exists():
            default_templates = {
                "photo": [
                    "{caption}",
                    "✨ {caption}",
                    "📸 {caption}",
                    "{caption} ✨",
                ],
                "video": [
                    "{caption}",
                    "🎥 {caption}",
                    "📹 {caption}",
                ],
                "reel": [
                    "{caption}",
                    "🎬 {caption}",
                    "✨ {caption}",
                    "{caption} 💯",
                ],
                "carousel": [
                    "{caption}",
                    "📸 {caption}",
                    "✨ {caption}",
                ],
            }
            with open(self.templates_file, "w", encoding="utf-8") as f:
                json.dump(default_templates, f, indent=2)
        
        if not self.hashtags_file.exists():
            default_hashtags = {
                "general": [
                    "#instagood", "#photooftheday", "#beautiful", "#picoftheday",
                    "#instadaily", "#photography", "#love", "#nature", "#art",
                ],
                "photo": [
                    "#photography", "#photo", "#photographer", "#photoshoot",
                ],
                "video": [
                    "#video", "#videography", "#videographer", "#videooftheday",
                ],
                "reel": [
                    "#reels", "#reelsinstagram", "#reel", "#reelitfeelit",
                    "#reelsvideo", "#reelsindia",
                ],
                "niche": [],
            }
            with open(self.hashtags_file, "w", encoding="utf-8") as f:
                json.dump(default_hashtags, f, indent=2)
    
    def _load_templates(self):
        """Load caption templates."""
        try:
            with open(self.templates_file, "r", encoding="utf-8") as f:
                self.templates = json.load(f)
        except Exception as e:
            logger.warning("Failed to load templates: %s", e)
            self.templates = {}
    
    def _load_hashtags(self):
        """Load hashtag pools."""
        try:
            with open(self.hashtags_file, "r", encoding="utf-8") as f:
                self.hashtag_pools = json.load(f)
        except Exception as e:
            logger.warning("Failed to load hashtags: %s", e)
            self.hashtag_pools = {}
    
    def generate_caption(
        self,
        media_type: str,
        base_caption: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """Generate caption from template."""
        variables = variables or {}
        variables.setdefault("caption", base_caption or "")
        variables.setdefault("date", datetime.now().strftime("%B %d, %Y"))
        variables.setdefault("time", datetime.now().strftime("%I:%M %p"))
        
        templates = self.templates.get(media_type, [])
        if not templates:
            return base_caption or ""
        
        template = random.choice(templates)
        
        try:
            caption = template.format(**variables)
        except KeyError:
            caption = base_caption or template
        
        return caption.strip()
    
    def get_hashtags(
        self,
        media_type: str,
        count: int = 10,
        pools: Optional[List[str]] = None,
    ) -> List[str]:
        """Get random hashtags from pools."""
        pools = pools or ["general", media_type]
        
        all_hashtags = []
        for pool_name in pools:
            if pool_name in self.hashtag_pools:
                all_hashtags.extend(self.hashtag_pools[pool_name])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_hashtags = []
        for tag in all_hashtags:
            if tag not in seen:
                seen.add(tag)
                unique_hashtags.append(tag)
        
        # Shuffle and return requested count
        random.shuffle(unique_hashtags)
        return unique_hashtags[:count]
    
    def format_caption_with_hashtags(
        self,
        caption: str,
        hashtags: List[str],
        hashtag_position: str = "end",
    ) -> str:
        """Format caption with hashtags."""
        hashtag_str = " ".join(hashtags)
        
        if hashtag_position == "end":
            return f"{caption}\n\n{hashtag_str}" if hashtags else caption
        elif hashtag_position == "beginning":
            return f"{hashtag_str}\n\n{caption}" if hashtags else caption
        else:  # separate
            return f"{caption}\n\n{hashtag_str}" if hashtags else caption
    
    def add_template(self, media_type: str, template: str):
        """Add a new caption template."""
        if media_type not in self.templates:
            self.templates[media_type] = []
        self.templates[media_type].append(template)
        self._save_templates()
    
    def add_hashtags(self, pool_name: str, hashtags: List[str]):
        """Add hashtags to a pool."""
        if pool_name not in self.hashtag_pools:
            self.hashtag_pools[pool_name] = []
        self.hashtag_pools[pool_name].extend(hashtags)
        self._save_hashtags()
    
    def _save_templates(self):
        """Save templates to file."""
        with open(self.templates_file, "w", encoding="utf-8") as f:
            json.dump(self.templates, f, indent=2)
    
    def _save_hashtags(self):
        """Save hashtags to file."""
        with open(self.hashtags_file, "w", encoding="utf-8") as f:
            json.dump(self.hashtag_pools, f, indent=2)
