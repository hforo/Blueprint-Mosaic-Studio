from config import *
from image import process_image
from render import render_master
from pages import render_pages


def main():

    project = process_image(
        IMAGE_FILE,
        GRID_WIDTH,
        GRID_HEIGHT,
        NUMBER_OF_COLORS,
    )

    render_master(project)
    render_pages(project)


if __name__ == "__main__":
    main()