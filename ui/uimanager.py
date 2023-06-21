import spotipy
from spotipy import SpotifyOAuth

import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
import configparser

from main import sync_music_library


def open_options_window():
    def browse_download_path():
        download_path = filedialog.askdirectory()
        if download_path:
            download_path_entry.delete(0, tk.END)
            download_path_entry.insert(tk.END, download_path)

    def browse_cookies_file():
        cookies_file = filedialog.askopenfilename()
        if cookies_file:
            cookies_file_entry.delete(0, tk.END)
            cookies_file_entry.insert(tk.END, cookies_file)

    def save_options():
        download_path = download_path_entry.get()
        cookies_file = cookies_file_entry.get()

        config = configparser.ConfigParser()
        config.read('config.ini')

        # Update the download path
        config.set('Settings', 'download_path', download_path)

        # Add or update the cookies file path
        if cookies_file:
            config.set('Settings', 'cookies_file', cookies_file)

        with open('../config.ini', 'w') as config_file:
            config.write(config_file)

        messagebox.showinfo("Options Saved", "Options saved successfully.")

    # Create the options window
    options_window = tk.Toplevel()
    options_window.title("Options")

    # Download Path Label and Entry
    download_path_label = tk.Label(options_window, text="Download Path:")
    download_path_label.pack()

    download_path_entry = tk.Entry(options_window)
    download_path_entry.pack()

    browse_path_button = tk.Button(options_window, text="Browse", command=browse_download_path)
    browse_path_button.pack()

    # Cookies File Label and Entry
    cookies_file_label = tk.Label(options_window, text="Cookies File:")
    cookies_file_label.pack()

    cookies_file_entry = tk.Entry(options_window)
    cookies_file_entry.pack()

    browse_cookies_button = tk.Button(options_window, text="Browse", command=browse_cookies_file)
    browse_cookies_button.pack()

    # Save Options Button
    save_button = tk.Button(options_window, text="Save Options", command=save_options)
    save_button.pack()


def create_main_window():
    # Create the main window
    window = tk.Tk()
    window.title("Music Library Sync")

    # Sync Music Library Button
    sync_button = tk.Button(window, text="Sync Music Library", command=sync_music_library)
    sync_button.pack()

    # Open Options Window Button
    options_button = tk.Button(window, text="Options", command=open_options_window)
    options_button.pack()

    # Start the Tkinter event loop
    window.mainloop()