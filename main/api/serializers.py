from rest_framework import serializers

from main.application.config_validation import ConfigurationInputValidator
from main.domain.configuration import ConfigValidationError
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
    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, "instance", None)
        device = attrs.get("device") or getattr(instance, "device", None)
        config_text = attrs.get("config_text", getattr(instance, "config_text", ""))
        if device and config_text:
            try:
                ConfigurationInputValidator.validate_backup_input_or_raise(
                    device=device,
                    config_text=config_text,
                )
            except ConfigValidationError as exc:
                raise serializers.ValidationError(str(exc)) from exc
        return attrs

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
