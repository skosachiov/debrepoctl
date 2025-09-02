import os
import gzip
import shutil
import requests
from urllib.parse import urljoin
from urllib.parse import urlparse
from datetime import datetime
import time


def update_debian_metadata_if_newer(base_url, local_base_dir):
    """
    Check if specific Debian metadata files are newer than local ones and update if needed.
    Builds local paths from URL structure.
    Returns True if updated, False if no update needed.
    """
    # Specific metadata files to check
    metadata_dirs = [
        'db/references.db',
        'indices/files/arch-amd64.files',
        'indices/files/components/source.list.gz'
    ]
    
    # Base local directory
    os.makedirs(local_base_dir, exist_ok=True)
    
    updated = False
    
    for metadata_dir in metadata_dirs:
        url = base_url + metadata_dir
        try:
            # Build local path from URL
            parsed_url = urlparse(url)
            # Remove leading slash and split path
            url_path = parsed_url.path.lstrip('/')
            local_path = os.path.join(local_base_dir, url_path)
            
            # Create directory structure if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Check if file exists locally
            if os.path.exists(local_path):
                local_mtime = os.path.getmtime(local_path)
                
                # Get remote file headers to check last-modified
                head_response = requests.head(url)
                head_response.raise_for_status()
                
                if 'last-modified' in head_response.headers:
                    remote_time_str = head_response.headers['last-modified']
                    remote_time = datetime.strptime(remote_time_str, '%a, %d %b %Y %H:%M:%S %Z').timestamp()
                    
                    if remote_time > local_mtime:
                        print(f"Updating {url_path} (remote is newer)")
                        # Download the updated file
                        file_response = requests.get(url)
                        file_response.raise_for_status()
                        
                        with open(local_path, 'wb') as f:
                            f.write(file_response.content)
                        
                        # Update local modification time to match remote
                        os.utime(local_path, (remote_time, remote_time))
                        
                        # Extract gzip file if it's a .gz file
                        if local_path.endswith('.gz'):
                            extract_path = local_path[:-3]  # Remove .gz extension
                            try:
                                with gzip.open(local_path, 'rb') as f_in:
                                    with open(extract_path, 'wb') as f_out:
                                        shutil.copyfileobj(f_in, f_out)
                                # Set same modification time for extracted file
                                os.utime(extract_path, (remote_time, remote_time))
                                print(f"Extracted to {extract_path}")
                            except Exception as e:
                                print(f"Error extracting {local_path}: {e}")
                        
                        updated = True
                    else:
                        print(f"{url_path} is up to date")
                else:
                    print(f"No last-modified header for {url}")
            else:
                # File doesn't exist locally, download it
                print(f"Downloading new file: {url_path}")
                file_response = requests.get(url)
                file_response.raise_for_status()
                
                with open(local_path, 'wb') as f:
                    f.write(file_response.content)
                
                # Set modification time from server if available
                if 'last-modified' in file_response.headers:
                    remote_time_str = file_response.headers['last-modified']
                    remote_time = datetime.strptime(remote_time_str, '%a, %d %b %Y %H:%M:%S %Z').timestamp()
                    os.utime(local_path, (remote_time, remote_time))
                
                # Extract gzip file if it's a .gz file
                if local_path.endswith('.gz'):
                    extract_path = local_path[:-3]  # Remove .gz extension
                    try:
                        with gzip.open(local_path, 'rb') as f_in:
                            with open(extract_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        # Set same modification time for extracted file
                        if 'last-modified' in file_response.headers:
                            os.utime(extract_path, (remote_time, remote_time))
                        print(f"Extracted to {extract_path}")
                    except Exception as e:
                        print(f"Error extracting {local_path}: {e}")
                
                updated = True
                
        except requests.RequestException as e:
            print(f"Error processing {url}: {e}")
            continue
    
    return updated

def get_distributions(base_url):
    """Get list of distributions from the Debian repository"""
    try:
        response = requests.get(base_url)
        response.raise_for_status()
        
        # Parse distributions from the directory listing
        distributions = []
        for line in response.text.split('\n'):
            if 'href="' in line and 'Parent Directory' not in line:
                # Extract distribution name from href
                start = line.find('href="') + 6
                end = line.find('"', start)
                dist = line[start:end].rstrip('/')
                if dist and not dist.startswith(('.', '?')):
                    distributions.append(dist)
        
        return distributions
    
    except requests.RequestException as e:
        print(f"Error fetching distributions: {e}")
        return []

def should_download_file(local_path, remote_last_modified):
    """Check if local file is older than remote file or doesn't exist"""
    if not os.path.exists(local_path):
        return True
    
    local_mtime = os.path.getmtime(local_path)
    local_time = datetime.fromtimestamp(local_mtime)
    
    # Parse remote last-modified date
    remote_time = datetime.strptime(remote_last_modified, '%a, %d %b %Y %H:%M:%S %Z')
    
    return local_time < remote_time

def download_file(url, local_path):
    """Download a file if local version is older or doesn't exist"""
    try:
        # Get file info first to check last-modified
        head_response = requests.head(url)
        head_response.raise_for_status()
        
        last_modified = head_response.headers.get('last-modified')
        if not last_modified:
            print(f"No last-modified header for {url}, forcing download")
            last_modified = "Thu, 01 Jan 1970 00:00:00 GMT"  # Force download
        
        if should_download_file(local_path, last_modified):
            print(f"Downloading: {url}")
            response = requests.get(url)
            response.raise_for_status()
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Save the file
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            # Set file modification time to match remote
            remote_time = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S %Z')
            timestamp = time.mktime(remote_time.timetuple())
            os.utime(local_path, (timestamp, timestamp))
            
            return True
        else:
            print(f"Skipping (up to date): {os.path.basename(local_path)}")
            return False
            
    except requests.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return False

def extract_gz_file(gz_path, output_path):
    """Extract .gz file to output path"""
    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"Extracted: {os.path.basename(output_path)}")
    except Exception as e:
        print(f"Error extracting {gz_path}: {e}")

def update_debian_metadata(base_url, local_base_dir):
    """Main function to update Debian repository metadata"""

    try:
        os.remove(local_base_dir + "/status")
    except Exception as e:
        pass

    print("Fetching distributions list...")
    distributions = get_distributions(base_url + "/dists/")
    
    if not distributions:
        print("No distributions found!")
        return
    
    print(f"Found {len(distributions)} distributions: {', '.join(distributions)}")
    
    # Files to download for each distribution
    metadata_files = [
        "main/binary-amd64/Packages.gz",
        "main/source/Sources.gz"
    ]
    
    for dist in distributions:
        print(f"\nProcessing distribution: {dist}")
        dist_url = urljoin(base_url, "dists/" + dist + "/")
        dist_dir = os.path.join(local_base_dir, "dists/" + dist)
        
        for file_path in metadata_files:
            # Download .gz file
            remote_url = urljoin(dist_url, file_path)
            local_gz_path = os.path.join(dist_dir, file_path)
            
            if download_file(remote_url, local_gz_path):
                # Extract the .gz file
                output_filename = os.path.basename(file_path).replace('.gz', '')
                output_dir = os.path.dirname(local_gz_path)
                output_path = os.path.join(output_dir, output_filename)
                
                extract_gz_file(local_gz_path, output_path)
    
    with open(local_base_dir + "/status", "w") as f:
        f.write(str(time.time()))

def main():
    """Main entry point"""
    base_url = "https://ftp.debian.org/debian/"
    local_base_dir = "./debian_metadata"
    if not update_debian_metadata_if_newer(base_url, local_base_dir):
        print("Specific remote metadata files are older, no need to update")
        if os.path.exists(local_base_dir + "/status"):
            return
    print("Starting Debian metadata update...")
    update_debian_metadata(base_url, local_base_dir)
    print("Metadata update completed!")

if __name__ == "__main__":
    main()
