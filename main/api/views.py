from dcim.models import Device
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework import serializers
from rest_framework.response import Response

from main.api.serializers import (
    CommandTemplateSerializer,
    ConfigurationBackupSerializer,
    DeviceCredentialSerializer,
    DevicePlatformProfileSerializer,
    NetworkTaskSerializer,
    ScheduledTaskSerializer,
    UMLConfigurationSerializer,
)
from main.models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)
from main.application.backups import ConfigurationService


class DeviceCredentialViewSet(NetBoxModelViewSet):
    queryset = DeviceCredential.objects.all()
    serializer_class = DeviceCredentialSerializer


class CommandTemplateViewSet(NetBoxModelViewSet):
    queryset = CommandTemplate.objects.all()
    serializer_class = CommandTemplateSerializer


class DevicePlatformProfileViewSet(NetBoxModelViewSet):
    queryset = DevicePlatformProfile.objects.all()
    serializer_class = DevicePlatformProfileSerializer


class NetworkTaskViewSet(NetBoxModelViewSet):
    queryset = NetworkTask.objects.all()
    serializer_class = NetworkTaskSerializer


class ConfigurationBackupViewSet(NetBoxModelViewSet):
    queryset = ConfigurationBackup.objects.all()
    serializer_class = ConfigurationBackupSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="device_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="NetBox device ID.",
            ),
        ],
        responses={
            200: ConfigurationBackupSerializer(many=True),
            400: OpenApiResponse(description="device_id query parameter is required."),
            404: OpenApiResponse(description="Device not found."),
        },
    )
    @action(detail=False, methods=['get'])
    def by_device(self, request):
        """List all saved configurations for a specific device."""
        device_id = request.query_params.get('device_id')
        if not device_id:
            return Response({'error': 'device_id query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return Response({'error': 'Device not found'}, status=status.HTTP_404_NOT_FOUND)
        
        versions = ConfigurationBackup.objects.filter(device=device).order_by('-version')
        serializer = self.get_serializer(versions, many=True)
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="from",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Source configuration backup ID.",
            ),
            OpenApiParameter(
                name="to",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Target configuration backup ID.",
            ),
        ],
        responses={
            200: inline_serializer(
                name="ConfigurationCompareResponse",
                fields={
                    "device_id": serializers.IntegerField(),
                    "device_name": serializers.CharField(),
                    "from_version": serializers.IntegerField(),
                    "from_version_name": serializers.CharField(allow_blank=True, allow_null=True),
                    "to_version": serializers.IntegerField(),
                    "to_version_name": serializers.CharField(allow_blank=True, allow_null=True),
                    "diff": serializers.ListField(child=serializers.CharField()),
                },
            ),
            400: OpenApiResponse(description="Missing query parameters or versions from different devices."),
            404: OpenApiResponse(description="One or both configurations not found."),
        },
    )
    @action(detail=False, methods=['get'])
    def compare(self, request):
        """Compare two configuration versions and return diff"""
        version_from_id = request.query_params.get('from')
        version_to_id = request.query_params.get('to')
        
        if not version_from_id or not version_to_id:
            return Response(
                {'error': 'Both from and to query parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            backup_from = ConfigurationBackup.objects.get(id=version_from_id)
            backup_to = ConfigurationBackup.objects.get(id=version_to_id)
        except ConfigurationBackup.DoesNotExist:
            return Response({'error': 'One or both configurations not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if backup_from.device != backup_to.device:
            return Response(
                {'error': 'Cannot compare versions from different devices'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        diff_lines = ConfigurationService.compare_versions(
            backup_from.config_text,
            backup_to.config_text
        )
        
        return Response({
            'device_id': backup_from.device.id,
            'device_name': backup_from.device.name,
            'from_version': backup_from.version,
            'from_version_name': backup_from.version_name,
            'to_version': backup_to.version,
            'to_version_name': backup_to.version_name,
            'diff': diff_lines
        })


class ScheduledTaskViewSet(NetBoxModelViewSet):
    queryset = ScheduledTask.objects.all()
    serializer_class = ScheduledTaskSerializer


class UMLConfigurationViewSet(NetBoxModelViewSet):
    queryset = UMLConfiguration.objects.all()
    serializer_class = UMLConfigurationSerializer
