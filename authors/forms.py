from django import forms
from .models import Author, Post


class AuthorForm(forms.ModelForm):
    """
    This form allows authors to edit their profile safely.

    Using Django ModelForm ensures:
    - Only allowed fields can be edited
    - Identity fields like UUID & URL remain protected
    - Data validation is handled automatically
    """

    class Meta:

        model = Author

        # These fields represent editable identity metadata.
        # UUID, host, & URL are excluded to preserve identity consistency.
        fields = [
            'displayName',
            'description',
            'github',
            'profileImage',
        ]

        # Use the labels dictionary to add spaces and fix casing for edit profile
        labels = {
            'displayName': 'Display Name',
            'description': 'Description',
            'github': 'GitHub Profile',
            'profileImage': 'Profile Image',
        }

    class PostForm(forms.ModelForm):
        class Meta:
            model = Post
            fields = [
                'title',
                'content',
                'visibility',
            ]
            labels = { 'visibility': 'Choose who can see this post' }