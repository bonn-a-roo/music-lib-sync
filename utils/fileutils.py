import os
import re



def create_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def sanitize_filename(filename):
    # Remove characters not allowed in Windows filenames
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)

    # Remove characters not allowed in Python variables
    filename = re.sub(r'\W+', '_', filename)

    return filename


