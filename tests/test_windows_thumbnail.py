from PIL import Image

from yt_downloader.infrastructure.windows_thumbnail import images_visually_similar


def test_visual_thumbnail_comparison_tolerates_small_overlay_but_rejects_different_frame() -> None:
    reference = Image.new("RGB", (320, 180), "#1267B0")
    overlay = reference.copy()
    for x in range(280, 310):
        for y in range(140, 170):
            overlay.putpixel((x, y), (255, 255, 255))
    different = Image.new("RGB", (320, 180), "#D13438")

    assert images_visually_similar(reference, overlay)
    assert not images_visually_similar(reference, different)
