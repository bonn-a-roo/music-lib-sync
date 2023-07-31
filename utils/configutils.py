import configparser


def ask_download_path():
    while True:
        download_path = input("Enter the download path: ")
        if download_path.strip():
            return download_path
        else:
            print("Invalid input. Please provide a valid download path.")


def get_download_path():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config.get('Settings', 'download_path')
