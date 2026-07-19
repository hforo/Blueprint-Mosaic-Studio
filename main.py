from config import *
from image import process_image
from render import render_master


def main():

    print("Loading image...")

    data = process_image(
        IMAGE_FILE,
        GRID_WIDTH,
        GRID_HEIGHT,
        NUMBER_OF_COLORS,
    )

    print("Rendering blueprint...")

    render_master(data)

    print("Done!")


if __name__ == "__main__":
    main()