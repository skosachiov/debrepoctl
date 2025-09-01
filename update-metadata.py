import os
import gzip
import shutil
import requests
from urllib.parse import urljoin
from datetime import datetime
import time

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

def update_debian_metadata():
    """Main function to update Debian repository metadata"""
    base_url = "https://ftp.debian.org/debian/dists/"
    local_base_dir = "./debian_metadata"
    
    print("Fetching distributions list...")
    distributions = get_distributions(base_url)
    
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
        dist_url = urljoin(base_url, dist + "/")
        dist_dir = os.path.join(local_base_dir, dist)
        
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

def main():
    """Main entry point"""
    print("Starting Debian metadata update...")
    update_debian_metadata()
    print("\nMetadata update completed!")

if __name__ == "__main__":
    main()
