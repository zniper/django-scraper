from django.dispatch.dispatcher import receiver
from django.db.models.signals import pre_delete

from .models import LocalContent


@receiver(pre_delete, sender=LocalContent)
def clear_local_files(sender, instance, *args, **kwargs):
    """Ensure all files saved into media dir will be deleted as well"""
    instance.remove_files()
