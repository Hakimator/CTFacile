from rest_framework import serializers
from core.models import User, Challenge, Category, Submission
from core.services.scoring_service import ScoringService


class FlagSubmissionSerializer(serializers.Serializer):
    """
    Validates the incoming JSON payload for submitting a flag.
    Strictly uses Serializer (not ModelSerializer) as the DB logging
    is handled decoupled inside the FlagValidationService.
    """

    challenge_id = serializers.IntegerField(
        required=True, help_text="The ID of the Challenge being attempted."
    )
    submitted_flag = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="The plain-text flag string submitted by the user.",
    )


class StartChallengeSerializer(serializers.Serializer):
    """
    Validates the incoming JSON payload for requesting a dynamic Docker challenge.
    """

    challenge_id = serializers.IntegerField(
        required=True, help_text="The ID of the Challenge container being requested."
    )


class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "password", "email"]
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        user = User(
            username=validated_data["username"], email=validated_data.get("email", "")
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


class JoinTeamSerializer(serializers.Serializer):
    join_code = serializers.UUIDField(
        required=True, help_text="The UUID invite code for the team."
    )


class ChallengeNodeSerializer(serializers.ModelSerializer):
    has_docker = serializers.SerializerMethodField()
    prerequisite_ids = serializers.SerializerMethodField()
    is_solved = serializers.SerializerMethodField()
    current_points = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            "id",
            "title",
            "description",
            "is_tutorial",
            "is_entry_node",
            "has_docker",
            "prerequisite_ids",
            "is_solved",
            "current_points",
        ]

    def get_has_docker(self, obj):
        return bool(obj.docker_image_tag)

    def get_prerequisite_ids(self, obj):
        # Extracts IDs from the ChallengePrerequisite pivot table
        return list(obj.prerequisites.values_list("required_challenge_id", flat=True))

    def get_is_solved(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        team = request.user.teams.first()
        if not team:
            return False

        return Submission.objects.filter(
            team=team, challenge=obj, is_correct=True
        ).exists()

    def get_current_points(self, obj):
        # Defers strictly to the shared Redis scoring service
        return ScoringService.calculate_dynamic_points(obj.id, obj.base_points)


class CategoryTreeSerializer(serializers.ModelSerializer):
    challenges = ChallengeNodeSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "description", "challenges"]
