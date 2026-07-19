"""Generate printable pages."""

from math import ceil
from PIL import Image, ImageDraw
from config import BORDER,CELL_SIZE,PAGE_COLUMNS,PAGE_ROWS,PAGES_FOLDER,PROJECT_NAME,TOTAL_PAGES
from render import load_fonts,draw_cell,draw_grid,draw_row_labels,draw_column_labels

def render_pages(project):
    PAGES_FOLDER.mkdir(exist_ok=True)
    title_font,header_font,cell_font=load_fonts()
    cols=ceil(project.width/PAGE_COLUMNS)
    rows=ceil(project.height/PAGE_ROWS)
    page=1
    for pr in range(rows):
        for pc in range(cols):
            sr=pr*PAGE_ROWS
            sc=pc*PAGE_COLUMNS
            er=min(sr+PAGE_ROWS,project.height)
            ec=min(sc+PAGE_COLUMNS,project.width)
            w=ec-sc
            h=er-sr
            canvas=Image.new("RGB",(w*CELL_SIZE+BORDER*2,h*CELL_SIZE+BORDER*2),"white")
            draw=ImageDraw.Draw(canvas)
            draw.text((BORDER,20),f"{PROJECT_NAME}  Page {page} of {TOTAL_PAGES}",font=title_font,fill="black")
            draw.text((BORDER,50),f"Columns {sc+1}-{ec}   Rows {sr+1}-{er}",font=header_font,fill="black")
            for r in range(sr,er):
                for c in range(sc,ec):
                    draw_cell(draw,project.grid[r][c],cell_font,row_offset=sr,col_offset=sc)
            draw_grid(draw,w,h)
            draw_row_labels(draw,header_font,h)
            draw_column_labels(draw,header_font,w)
            canvas.save(PAGES_FOLDER/f"Page_{page:02}.png",optimize=True)
            page+=1
