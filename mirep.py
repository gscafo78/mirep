import argparse
import requests
import os
import lzma
import logging
import subprocess
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import gzip
import shutil
import sys


'''
@author: Giovanni SCAFETTA
@version: 0.1.6
@description: This script is realized to clone an on line mirror of a Debian/Ubuntu repository to create your local repository.
@usage: python3 mirep.py -u <url> -p <protocol> -r <rootpath> -d <distributions> -c <components> -a <architectures> -i <inpath> -t <threads> -v
@example: python3 mirep.py -u ftp.debian.org/debian -p http -r /home/user/debian -d bullseye -c main -a amd64 -i debian -t 4 -v
@license: MIT
'''



VERSION = "0.1.6"

import logging

class Logger:
  @staticmethod
  def setup_logging(debug):
      """
      Sets up the logging configuration.

      Parameters:
      debug (bool): If True, sets the logging level to DEBUG. Otherwise, sets it to INFO.
      """
      # Determine the logging level based on the debug flag
      level = logging.DEBUG if debug else logging.INFO
      
      # Configure the logging settings
      logging.basicConfig(
          level=level,  # Set the logging level
          format='%(asctime)s - %(levelname)s - %(message)s',  # Define the log message format
      )

class Downloader:
  def __init__(self, proto, url, rootpath):
      """
      Initializes the Downloader with protocol, URL, and root path.

      Parameters:
      proto (str): The protocol to use (e.g., 'http', 'https').
      url (str): The base URL for downloading.
      rootpath (str): The root path where files will be downloaded.
      """
      self.proto = proto
      self.url = url
      self.rootpath = rootpath
      self.downloaded_files = []  # List to store paths of downloaded files
      self.downloaded_count = 0  # Counter for successfully downloaded files
      self.skipped_count = 0  # Counter for skipped files

  def download_directory(self, path, exclude_pattern="index.html*"):
      """
      Downloads a directory from the specified path, excluding certain files.

      Parameters:
      path (str): The path to the directory to download.
      exclude_pattern (str): Pattern of files to exclude from download.
      """
      parsed_url = path.split('/')[0]
      
      # Command to download the directory using wget
      command = [
          "wget", "-r", "-np", "-nH",
          "-P", f"{self.rootpath}/{parsed_url}",
          "--reject", exclude_pattern, f"{self.proto}://{path}"
      ]

      try:
          # Run the wget command and suppress output
          with open(os.devnull, 'w') as devnull:
              subprocess.run(command, check=True, stdout=devnull, stderr=devnull)
          logging.debug(f"Download completed successfully for {path}")
          # Add downloaded files to the list
          self._add_downloaded_files_from_directory(path)
      except subprocess.CalledProcessError as e:
          if e.returncode == 8:
              logging.debug(f"File does not exist: {path}")
          else:
              logging.error(f"An error occurred: {e}")

  def download_file(self, path, full_path, overwrite=False):
      """
      Downloads a single file from the specified path.

      Parameters:
      path (str): The URL of the file to download.
      full_path (str): The full path where the file will be saved.
      overwrite (bool): Whether to overwrite the file if it already exists.
      """
      folder = os.path.dirname(full_path)
      if not os.path.exists(folder):
          os.makedirs(folder, exist_ok=True)
          logging.debug(f"Created directory: {folder}")

      file_name = os.path.basename(full_path)
      if os.path.exists(full_path) and not overwrite:
          logging.debug(f"File '{file_name}' already exists. Skipping download.")
          self.skipped_count += 1  # Increment skipped count
          return

      try:
          # Request the file from the URL
          response = requests.get(path, stream=True)
          response.raise_for_status()
          total_size = int(response.headers.get('content-length', 0))
          with open(full_path, 'wb') as file, tqdm(
              desc=file_name,
              total=total_size,
              unit='B',
              unit_scale=True,
              unit_divisor=1024
          ) as bar:
              for chunk in response.iter_content(chunk_size=8192):
                  file.write(chunk)
                  bar.update(len(chunk))
          logging.debug(f"File '{file_name}' downloaded successfully.")
          self.downloaded_files.append(full_path)  # Add to the list
          self.downloaded_count += 1  # Increment downloaded count
      
      except requests.exceptions.HTTPError as e:
          if response.status_code == 404:
              logging.error(f"Failed to download the file: {e}")
          else:
              logging.error(f"An error occurred: {e}")

  def _add_downloaded_files_from_directory(self, path):
      """
      Adds files downloaded by wget to the list of downloaded files.

      Parameters:
      path (str): The path to the directory where files were downloaded.
      """
      for root, _, files in os.walk(f"{self.rootpath}/{path}"):
          for file in files:
              self.downloaded_files.append(os.path.join(root, file))

  def get_downloaded_files(self):
      """
      Returns the list of downloaded files.

      Returns:
      list: A list of paths to the downloaded files.
      """
      return self.downloaded_files

  def get_downloaded_count(self):
      """
      Returns the count of successfully downloaded files.

      Returns:
      int: The number of downloaded files.
      """
      return self.downloaded_count

  def get_skipped_count(self):
      """
      Returns the count of skipped files.

      Returns:
      int: The number of skipped files.
      """
      return self.skipped_count
  

class PackageHandler:
  @staticmethod
  def parse_packages_file(file_path):
      """
      Parses a package file and returns a list of package dictionaries.

      Parameters:
      file_path (str): The path to the package file.

      Returns:
      list: A list of dictionaries, each representing a package.
      """
      packages = []
      current_package = {}

      with open(file_path, 'r') as file:
          for line in file:
              line = line.strip()
              if not line:
                  # If a blank line is encountered, save the current package and reset
                  if current_package:
                      packages.append(current_package)
                      current_package = {}
              else:
                  if ': ' in line:
                      # Split the line into key and value
                      key, value = line.split(': ', 1)
                      current_package[key] = value
                  else:
                      # Handle continuation lines
                      last_key = next(reversed(current_package), None)
                      if last_key:
                          current_package[last_key] += ' ' + line

          # Add the last package if the file doesn't end with a blank line
          if current_package:
              packages.append(current_package)

      return packages

  @staticmethod
  def extract_file(file_path):
      """
      Extracts the contents of a file based on its extension.

      Parameters:
      file_path (str): The path to the file to extract.

      Returns:
      str: The extracted data as a string.
      """
      if file_path.endswith(".xz"):
          with lzma.open(file_path, 'rt') as file:
              data = file.read()
      elif file_path.endswith(".gz"):
          with gzip.open(file_path, 'rt') as file:
              data = file.read()
      else:
          with open(file_path, 'r') as file:
              data = file.read()
      
      print(f"Extracted data from {file_path}")
      return data

  @staticmethod
  def find_and_extract_packages(file_list):
      """
      Finds and extracts package data from a list of files.

      Parameters:
      file_list (list): A list of file paths to search for package files.

      Returns:
      list: A list of package dictionaries extracted from the files.
      """
      for file_path in file_list:
          if file_path.endswith("Packages") or file_path.endswith("Packages.xz") or file_path.endswith("Packages.gz"):
              data = PackageHandler.extract_file(file_path)
              # Parse the extracted data
              return PackageHandler.parse_packages_data(data)

  @staticmethod
  def parse_packages_data(data):
      """
      Parses package data from a string and returns a list of package dictionaries.

      Parameters:
      data (str): The package data as a string.

      Returns:
      list: A list of dictionaries, each representing a package.
      """
      packages = []
      current_package = {}
      lines = data.splitlines()

      for line in lines:
          line = line.strip()
          if not line:
              # If a blank line is encountered, save the current package and reset
              if current_package:
                  packages.append(current_package)
                  current_package = {}
          else:
              if ': ' in line:
                  # Split the line into key and value
                  key, value = line.split(': ', 1)
                  current_package[key] = value
              else:
                  # Handle continuation lines
                  last_key = next(reversed(current_package), None)
                  if last_key:
                      current_package[last_key] += ' ' + line

      # Add the last package if the data doesn't end with a blank line
      if current_package:
          packages.append(current_package)

      return packages

class FileManager:
  @staticmethod
  def list_files_recursive(folder_path):
      """
      Recursively lists all files in a given folder and its subfolders.

      Parameters:
      folder_path (str): The path to the folder to search.

      Returns:
      list: A list of file paths.
      """
      file_list = []
      for root, _, files in os.walk(folder_path):
          for file in files:
              # Append the full file path to the list
              file_list.append(os.path.join(root, file))
      return file_list

  @staticmethod
  def list_files_in_folder(folder_path):
      """
      Lists all files in a given folder, excluding subfolders.

      Parameters:
      folder_path (str): The path to the folder to search.

      Returns:
      list: A list of file paths.
      """
      try:
          # List all files and directories in the given folder
          files = os.listdir(folder_path)
          # Filter out directories, only keep files
          file_paths = [os.path.join(folder_path, f) for f in files if os.path.isfile(os.path.join(folder_path, f))]
          return file_paths
      except Exception as e:
          print(f"An error occurred: {e}")
          return []

  @staticmethod
  def delete_files(file_list):
      """
      Deletes a list of files.

      Parameters:
      file_list (list): A list of file paths to be deleted.

      Returns:
      None
      """
      for file_path in file_list:
          try:
              # Attempt to remove the file
              os.remove(file_path)
              print(f"Deleted: {file_path}")
          except FileNotFoundError:
              print(f"File not found: {file_path}")
          except PermissionError:
              print(f"Permission denied: {file_path}")
          except Exception as e:
              print(f"Error deleting {file_path}: {e}")

class RepositoryManage:

    def __init__(self, args):
        """
        Initializes the RepositoryManage with the given arguments.

        Parameters:
        args: An object containing configuration parameters such as protocol, URL, root path, etc.
        """
        self.args = args
        self.downloader = Downloader(args.proto, args.url, self.args.rootpath)

    def mirror_repository(self):
        """
        Mirrors a repository by downloading necessary files and directories.
        """
        link_list = []

        # List all files in the root path before filtering
        file_list = FileManager.list_files_recursive(f"{self.args.rootpath}/{self.args.url}")
        logging.debug(f"Files in root path before filtering: {file_list}")

        futures = []  # Maintain a single futures list
        with ThreadPoolExecutor(max_workers=self.args.threads) as executor:
            for distribution in self.args.distributions:
                # Download release files for each distribution
                for cert in ["InRelease", "Release", "Release.gpg"]:
                    common_path = f"{self.args.url}/{self.args.inpath}/dists/{distribution}/{cert}"
                    futures.append(executor.submit(
                        self.downloader.download_file,
                        f"{self.args.proto}://{common_path}",
                        f"{self.args.rootpath}/{common_path}",
                        True
                    ))

                for component in self.args.components:
                    # Download directories for each component
                    self.downloader.download_directory(f"{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/i18n/")
                    self.downloader.download_directory(f"{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/source/")

                    for arch in self.args.architectures:
                        # Download architecture-specific files
                        common_path = f"{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/Contents-{arch}.gz"
                        futures.append(executor.submit(
                            self.downloader.download_file,
                            f"{self.args.proto}://{common_path}",
                            f"{self.args.rootpath}/{common_path}",
                            True
                        ))
                        self.downloader.download_directory(f"{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/binary-{arch}/")
                        self.downloader.download_directory(f"{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/debian-installer/binary-{arch}/")
                        
                        # List and process package files
                        save_path = f"{self.args.rootpath}/{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/binary-{arch}/"
                        pack_files = FileManager.list_files_in_folder(save_path)
                        packages_info = PackageHandler.find_and_extract_packages(pack_files)
                        logging.debug(f"Pages Info: {len(packages_info)}")
                        for index, package in enumerate(packages_info, start=1):
                            logging.debug(f"Serial Number: {index}")
                            logging.debug(f"Package: {package.get('Package')}")
                            logging.debug(f"Version: {package.get('Version')}")
                            logging.debug(f"Description: {package.get('Description')}")
                            logging.debug(f"Filename: {package.get('Filename')}")
                            downloadlink = f"{self.args.proto}://{self.args.url}/{self.args.inpath}/{package.get('Filename')}"
                            filesave = f"{self.args.rootpath}/{self.args.url}/{self.args.inpath}/{package.get('Filename')}"
                            link_list.append(filesave)
                            futures.append(executor.submit(
                                self.downloader.download_file,
                                downloadlink,
                                filesave,
                                False
                            ))

        # Wait for all download tasks to complete
        for future in as_completed(futures):
            future.result()

        # Extend the link list with downloaded files
        link_list.extend(self.downloader.get_downloaded_files())
        logging.debug(f"Stored {len(file_list)} files.")
        logging.debug(f"link_list {len(link_list)}")

    def remove_repository(self):
        """
        Removes a repository by deleting files and directories.
        """
        file_list = []
        for distribution in self.args.distributions:
            for component in self.args.components:
                for arch in self.args.architectures:
                    # List and process package files
                    save_path = f"{self.args.rootpath}/{self.args.url}/{self.args.inpath}/dists/{distribution}/{component}/binary-{arch}/"
                    pack_files = FileManager.list_files_in_folder(save_path)
                    packages_info = PackageHandler.find_and_extract_packages(pack_files)
                    logging.debug(f"Pages Info: {len(packages_info)}")
                    for index, package in enumerate(packages_info, start=1):
                        logging.debug(f"Serial Number: {index}")
                        logging.debug(f"Package: {package.get('Package')}")
                        logging.debug(f"Version: {package.get('Version')}")
                        logging.debug(f"Description: {package.get('Description')}")
                        logging.debug(f"Filename: {package.get('Filename')}")
                        file_list.append(f"{self.args.rootpath}/{self.args.url}/{self.args.inpath}/{package.get('Filename')}")

        print(f"{len(file_list)} files to erase. Continue? (y/N)")
        # Capture and validate user input
        user_input = input().strip().lower()  # Convert input to lowercase for easier comparison

        # Default behavior is 'n'
        if user_input not in ['y', 'n']:
            user_input = 'n'

        # Proceed based on user input
        if user_input == 'y':
            # Code to delete the files
            for file_path in file_list:
                try:
                    logging.info(f"Deleting: {file_path}")
                    os.remove(file_path)
                except FileNotFoundError:
                    print(f"File not found: {file_path}")
                except PermissionError:
                    print(f"Permission denied: {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
            # Remove the distribution folder
            shutil.rmtree(f"{self.args.rootpath}/{self.args.url}/{self.args.inpath}/dists/{distribution}")
        else:
            print("Operation cancelled.")

def main():
  """
  Main function to parse command-line arguments and manage the repository mirroring or removal.
  """
  # Set up argument parser with a description of the script
  parser = argparse.ArgumentParser(description="Mirror a Debian/Ubuntu repository.")
  
  # Define required and optional command-line arguments
  parser.add_argument("--proto", required=True, help="Protocol to use (e.g., https/http)")
  parser.add_argument("--url", required=True, help="Base URL of the repository (e.g., ftp.debian.org)")
  parser.add_argument("--inpath", required=True, help="Path within the repository (e.g., debian)")
  parser.add_argument("--distributions", required=True, nargs='+', help="List of distributions (e.g., bullseye)")
  parser.add_argument("--components", required=True, nargs='+', help="List of components (e.g., main contrib non-free)")
  parser.add_argument("--architectures", required=True, nargs='+', help="List of architectures (e.g., amd64 i386 arm64 armel armhf ppc64el s390x riscv64)")
  parser.add_argument("--rootpath", required=True, help="Local root path to save files (e.g, /var/www/html/apt)")
  parser.add_argument("--threads", type=int, default=5, help="Number of threads to use (default: 5)")
  parser.add_argument("--remove", action='store_true', help="Remove local repository")
  parser.add_argument("--verbose", action='store_true', help="Verbose mode")
  parser.add_argument("--version", action='version', version=f"%(prog)s {VERSION}")

  try:
      # Parse the command-line arguments
      args = parser.parse_args()
  except SystemExit as e:
      # Handle missing or invalid arguments
      print("Error: Missing or invalid arguments.")
      parser.print_help()
      return

  # Set up logging based on the verbose flag
  Logger.setup_logging(args.verbose)
  
  # Create an instance of RepositoryManage with the parsed arguments
  mirror = RepositoryManage(args)
  
  try:
      # Check if the remove flag is set and call the appropriate method
      if mirror.args.remove:
          mirror.remove_repository()
      else:
          mirror.mirror_repository()
  except KeyboardInterrupt:
      # Handle Ctrl+C gracefully
      print("\nOperation cancelled by user.")
      sys.exit(0)

if __name__ == "__main__":
  main()