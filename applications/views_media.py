import boto3
from botocore.client import Config
from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from .r2 import generate_signed_url
from .permissions import can_view_documents
from .permissions import can_view_selection_media


def _presigned_get_url(key: str, expires: int = 300) -> str:
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )


@login_required
def view_document(request, key):
    if not can_view_documents(request.user):
        raise Http404()

    url = generate_signed_url(key, expires=300)
    return redirect(url)


def generate_signed_url(key: str, expires: int = 300) -> str:
    client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )

    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
        },
        ExpiresIn=expires,
    )


@login_required
def secure_document(request, key: str):
    """
    Secure document access for Admin + Scholarship Officer only.
    Generates a temporary signed URL from Cloudflare R2.
    """
    if not can_view_documents(request.user):
        raise Http404()

    signed_url = generate_signed_url(key, expires=300)
    return redirect(signed_url)

