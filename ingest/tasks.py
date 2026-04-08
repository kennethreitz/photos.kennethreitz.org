import logging

import imagehash
from celery import shared_task

from core.models import Image

logger = logging.getLogger(__name__)

PHASH_THRESHOLD = 10


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_image_task(self, image_id: str) -> None:
    """Async task to run the full ingest pipeline on an uploaded image."""
    from ingest.pipeline import process_image

    try:
        image = Image.objects.get(id=image_id)
    except Image.DoesNotExist:
        logger.error("Image %s not found, skipping processing", image_id)
        return

    try:
        process_image(image)

        # Post-processing perceptual dedup — batch load, compare in memory
        if image.perceptual_hash and image.perceptual_hash != '8000000000000000':
            upload_hash = imagehash.hex_to_hash(image.perceptual_hash)
            candidates = list(
                Image.objects.exclude(id=image.id)
                .exclude(perceptual_hash='')
                .exclude(perceptual_hash='8000000000000000')
                .values_list('id', 'perceptual_hash')
            )
            for cid, chash in candidates:
                if imagehash.hex_to_hash(chash) - upload_hash <= PHASH_THRESHOLD:
                    logger.info("Image %s is visual dupe of %s, deleting", image_id, cid)
                    image.delete()
                    return

        logger.info("Successfully processed image %s", image_id)
    except Exception as exc:
        logger.exception("Failed to process image %s", image_id)
        raise self.retry(exc=exc)
