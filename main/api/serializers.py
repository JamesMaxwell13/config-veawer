from rest_framework import serializers

from main.models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    GitLabConfigMapping,
    GitLabIntegration,
    GitLabSyncLog,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


class DeviceCredentialSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    enable_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = DeviceCredential
        fields = "__all__"


class CommandTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommandTemplate
        fields = "__all__"


class DevicePlatformProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DevicePlatformProfile
        fields = "__all__"


class GitLabIntegrationSerializer(serializers.ModelSerializer):
    access_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    webhook_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = GitLabIntegration
        fields = "__all__"

    def update(self, instance, validated_data):
        if not validated_data.get("access_token"):
            validated_data.pop("access_token", None)
        if not validated_data.get("webhook_secret"):
            validated_data.pop("webhook_secret", None)
        return super().update(instance, validated_data)


class GitLabConfigMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitLabConfigMapping
        fields = "__all__"


class GitLabSyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitLabSyncLog
        fields = "__all__"


class GitLabWebhookPayloadSerializer(serializers.Serializer):
    ref = serializers.CharField(required=False, allow_blank=True)
    checkout_sha = serializers.CharField(required=False, allow_blank=True)
    after = serializers.CharField(required=False, allow_blank=True)
    project = serializers.DictField(required=False)
    commits = serializers.ListField(child=serializers.DictField(), required=False)


class NetworkTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkTask
        fields = "__all__"


class ConfigurationBackupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationBackup
        fields = "__all__"


class ScheduledTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledTask
        fields = "__all__"


class UMLConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UMLConfiguration
        fields = "__all__"
