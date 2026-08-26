from PIL import Image
import matplotlib.pyplot as plt

# Open the multi-page TIFF
#img = Image.open('your_file.tif')
# Load the TIFF image
# img = Image.open(r"Z:\Lab Rice\Experimental Projects\Monolithic Trap\Axial drift\GEN3\drift_3MHz_3Vendcapavg\test1.tif")
img = Image.open(r"Z:\Lab Rice\Experimental Projects\Monolithic Trap\Axial drift\GEN3\test1.tif")


def find_maxima(img):

    hmax=0
    vmax=0


    return hmax,vmax

# Loop over each frame/page
i = 0
while True:
    try:
        img.seek(i)
        img_page = img.copy()

        # Display
        plt.imshow(img_page, cmap='gray')
        plt.title(f"Page {i}")
        plt.axis('off')
        plt.show()

        # Save each page separately
        #img_page.save(f'page_{i}.tif')
        i += 1
    except EOFError:
        break  # No more pages