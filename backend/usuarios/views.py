from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import roles, services
from .models import Bitacora
from .permissions import TieneRol
from .serializers import BitacoraSerializer, FiltroBitacoraSerializer


class LoginView(TokenObtainPairView):
    """Emite el par de tokens JWT y registra el intento en la bitácora."""

    serializer_class = TokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            services.registrar_evento(
                Bitacora.Accion.LOGIN_FALLIDO,
                nombre_usuario=str(request.data.get("username", "")),
                descripcion="Credenciales inválidas o usuario inactivo.",
                request=request,
            )
            raise AuthenticationFailed("Usuario o contraseña incorrectos.")
        usuario = serializer.user
        services.registrar_evento(Bitacora.Accion.LOGIN, usuario=usuario, request=request)
        return Response({**serializer.validated_data, "usuario": services.datos_usuario(usuario)})


class LogoutView(APIView):
    """Invalida el refresh token (lista negra) y registra el cierre de sesión."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response({"detail": "Falta el refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(token)
            if str(refresh.get("user_id")) != str(request.user.pk):
                return Response({"detail": "El token no pertenece al usuario."}, status=status.HTTP_400_BAD_REQUEST)
            refresh.blacklist()
        except TokenError:
            return Response({"detail": "Token inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)
        services.registrar_evento(Bitacora.Accion.LOGOUT, usuario=request.user, request=request)
        return Response({"detail": "Sesión cerrada."})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.datos_usuario(request.user))


class BitacoraListView(ListAPIView):
    serializer_class = BitacoraSerializer
    permission_classes = [TieneRol(roles.AUDITOR)]

    def get_queryset(self):
        filtros = FiltroBitacoraSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        return services.consultar_bitacora(**filtros.validated_data)


class UsuariosView(APIView):
    """Usuarios activos con sus roles (por ejemplo, para elegir el responsable de un centro).
    Filtro opcional `?rol=`."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuarios = User.objects.filter(is_active=True).prefetch_related("groups").order_by("first_name", "username")
        rol = request.query_params.get("rol")
        if rol:
            usuarios = usuarios.filter(groups__name=rol)
        return Response([services.datos_usuario(u) for u in usuarios])
