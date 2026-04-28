from rest_framework import serializers

from main.models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
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
