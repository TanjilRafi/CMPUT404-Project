from drf_spectacular.openapi import AutoSchema

# Google Gemini "can I set tags automatically based on authentication methods decorator in django swagger documentation"
class TagRemoteAPI(AutoSchema):
    def get_tags(self):
        # 1. Get the default tags (usually based on the URL or View name)
        #manual = super().get_tags()
        tags = super().get_tags()
        # 2. Inspect the authentication classes on the view
        auth_classes = getattr(self.view, 'authentication_classes', [])
        
        # 3. Logic to determine auth-based tags
        auth_names = [auth.__name__ for auth in auth_classes]
        # warning very circumstantial logic
        if (("NodeBasicAuthentication" in auth_names) or len(auth_names)==1) and (self.method == 'GET' or "inbox" in self.path):
            tags.append("Remote")
        else:
            tags.append("Local")

            # Example: Tag based on the specific class name
            # for auth_cls in auth_classes:
            #     tags.append(f"Auth: {auth_cls.__name__}")
        if tags:
            return tags
        return super().get_tags()