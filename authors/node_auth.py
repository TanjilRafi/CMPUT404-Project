import base64
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Node

# The following function was written with the assistance of Claude, 2025-03-20.
class NodeBasicAuthentication(BaseAuthentication):
    """
    Custom DRF authenticator for node-to-node HTTP Basic Auth (US 08.09).

    Remote nodes identify themselves with a username + password that a local node admin registered via the 
    Node model.  Cannot use Django's standard User table for this because remote nodes are not Django users, 
    they are peer servers whose credentials are managed entirely through the admin panel.

    If the Authorization header matches an enabled Node row, we return a sentinel (node, None) tuple so DRF 
    considers the request authenticated. The node object is attached to request.auth so views can inspect it.

    Returns None (not an error) when no Authorization header is present so that SessionAuthentication can 
    still handle browser-based requests on the same endpoint.
    """
    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header.startswith("Basic "):
            # Not a Basic Auth request; let the next authenticator try.
            return None

        try:
            # Decode the base64-encoded "username:password" credential string.
            decoded = base64.b64decode(
                auth_header[len("Basic "):].strip()
            ).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            raise AuthenticationFailed("Malformed Basic Auth header.")

        # Look up the credential pair against enabled nodes only.
        # Disabled nodes must be rejected even if the password is correct, because the admin disabled them intentionally.
        node = Node.objects.filter(
            username=username,
            password=password,
            is_enabled=True,
        ).first()

        if node is None:
            # Credentials don't match any enabled node; deny access.
            raise AuthenticationFailed(
                "Invalid node credentials or node is disabled."
            )

        # Return (user, auth) tuple. We use a sentinel string for the "user" position because DRF requires 
        # a non-None first element to consider the request authenticated. Views that need the node object 
        # can access request.auth.
        return ("node:" + node.url, node)

    def authenticate_header(self, request):
        # Tells clients what authentication scheme to use when returning 401.
        return 'Basic realm="SocialDistribution Node"'