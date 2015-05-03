from django.dispatch.dispatcher import receiver
from django.db.models.signals import pre_delete

from .models import LocalContent, Result


@receiver(pre_delete, sender=LocalContent)
def clear_local_files(sender, instance, *args, **kwargs):
    """Ensure all files saved into media dir will be deleted as well"""
    instance.remove_files()


@receiver(pre_delete, sender=Result)
def remove_result(sender, **kwargs):
    """Ensure all related local content will be deleted"""
    result = kwargs['instance']
    if result.other:
        result.other.delete()
