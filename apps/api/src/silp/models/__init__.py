"""مدل‌های SQLAlchemy. همه اینجا وارد می‌شوند تا Alembic آن‌ها را ببیند."""

from silp.db.base import Base
from silp.models.identity import (
    NULL_SCOPE,
    OTPChallenge,
    RefreshToken,
    Role,
    User,
    UserRole,
)
from silp.models.profile import (
    Profile,
    ProfileAsset,
    ProfileInterest,
    ProfileSkill,
    ProfileSurveyVersion,
)
from silp.models.project import (
    Project,
    ProjectApplication,
    ProjectInterest,
    ProjectRequiredAsset,
    ProjectRequiredSkill,
    ProjectRole,
    RecommendationFeedback,
    Team,
    TeamMember,
)
from silp.models.taxonomy import Asset, Interest, Skill, University

__all__ = [
    "NULL_SCOPE",
    "Asset",
    "Base",
    "Interest",
    "OTPChallenge",
    "Profile",
    "ProfileAsset",
    "ProfileInterest",
    "ProfileSkill",
    "ProfileSurveyVersion",
    "Project",
    "ProjectApplication",
    "ProjectInterest",
    "ProjectRequiredAsset",
    "ProjectRequiredSkill",
    "ProjectRole",
    "RecommendationFeedback",
    "RefreshToken",
    "Role",
    "Skill",
    "Team",
    "TeamMember",
    "University",
    "User",
    "UserRole",
]
