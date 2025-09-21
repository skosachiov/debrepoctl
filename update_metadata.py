#!/usr/bin/env python3

import os, gzip, shutil, requests
import time, argparse, logging, json, hashlib, re, apt_pkg, sys
from urllib.parse import urljoin, urlparse
from datetime import datetime

def md5_from_tuple(data_tuple):
    """Generate MD5 hash from a tuple using JSON serialization"""
    # Convert tuple to JSON string
    json_str = json.dumps(data_tuple)
    # Generate MD5 hash
    md5_hash = hashlib.md5(json_str.encode('utf-8'))
    return md5_hash.hexdigest()

def write_metadata_index(filename, data_dict):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('[\n')  # Start with list bracket
            items = []
            for item in data_dict.values():
                # Convert each item to JSON string without indentation
                item_str = json.dumps(item, separators=(',', ':'))
                items.append(f'  {item_str}')
            f.write(',\n'.join(items))
            f.write('\n]')  # End with list bracket
        logging.info(f"List successfully written to {filename}")
    except IOError as e:
        logging.error(f"Error writing to file: {e}")

def read_metadata_index(filename):
    if not os.path.exists(filename):
        logging.error(f"File {filename} does not exist")
        return {}
    data_dict = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
        for e in data_list:
            data_dict[md5_from_tuple((e["package"], e['version'], e['dist'], e['comp'], e['arch']))] = e
        logging.info(f"Dictionary successfully read from {filename}")
        return data_dict
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error reading file: {e}")
        return {}

def update_metadata_index(filename, data_dict, dist, comp, arch):
    packages = data_dict
    with open(filename, 'rt', encoding='utf-8') as f:
        content = f.read()
        # Split into individual package blocks
        package_blocks = re.split(r'\n\n+', content.strip())
        for block in package_blocks:
            pkg_name = version = source = source_version = None
            depends = []
            block_list = []
            for line in block.splitlines():
                if len(block_list) > 0 and block_list[-1][-1] == ',' and line[0].isspace():
                    block_list[-1] += line.rstrip()
                else:
                    if line:
                        block_list.append(line.rstrip())
            for line in block_list:
                if not line or line[0].isspace(): continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    # Extract package name
                    if key == 'Package':
                        if pkg_name != None:
                            logging.error(f'Duplicate stanza key: {key}: {value.strip()}')
                        pkg_name = value.strip()
                    # Build binary-to-source mapping for binary metadata if requested
                    if key == 'Source':
                        source_line = value.strip().split()
                        if len(source_line) > 0:
                            source = source_line[0]
                            if len(source_line) > 1: source_version = re.findall(r'\((.*?)\)', source_line[1])[0]
                   # Extract version
                    if key == 'Version':
                        version = value.strip()
                    # Collect dependencies
                    if key in ('Build-Depends', 'Build-Depends-Indep', 'Build-Depends-Arch', 'Depends', 'Pre-Depends'):
                        deps_pkgs = [p.strip().split()[0].split(":")[0] for p in value.split(',') if p.strip()]
                        for p in deps_pkgs:
                            depends.append(p)
            # Store package metadata if valid
            if pkg_name != None:
                if md5_from_tuple((pkg_name, version, dist, comp, arch)) not in packages:
                    if source == None: source = pkg_name
                    if source_version == None: source_version = version
                    packages[md5_from_tuple((pkg_name, version, dist, comp, arch))] = { \
                        'package': pkg_name, 'version': version, 'dist': dist, 'comp': comp, 'arch': arch, \
                        'depends': hashlib.md5(",".join(depends).encode()).hexdigest()[:8], \
                        'source': source, 'source_version': source_version}
    logging.debug(f'In the file {filename} processed packets: {len(packages)}')
    return packages

def parse_requirement_line(line):
    """
    Parse a Debian requirement line into (package_name, operator, version)
    Handles: =, >=, <=, >>, <<
    """
    line = line.strip()
    if not line or line.endswith(')'):
        return None
    
    # Handle cases with version constraints
    if '(' in line and ')' in line:
        package_part = line.split('(')[0].strip()
        constraint_part = line.split('(')[1].split(')')[0].strip()
        
        # Parse constraint part - check for Debian operators
        if constraint_part.startswith('= '):
            version = constraint_part[2:].strip()
            return (package_part, '=', version)
        elif constraint_part.startswith('='):
            version = constraint_part[1:].strip()
            return (package_part, '=', version)
        elif constraint_part.startswith('>='):
            version = constraint_part[2:].strip()
            return (package_part, '>=', version)
        elif constraint_part.startswith('<='):
            version = constraint_part[2:].strip()
            return (package_part, '<=', version)
        elif constraint_part.startswith('>>'):
            version = constraint_part[2:].strip()
            return (package_part, '>>', version)
        elif constraint_part.startswith('<<'):
            version = constraint_part[2:].strip()
            return (package_part, '<<', version)
    
    return None

def check_version(version, required_op, required_version):
    """
    Check if installed version satisfies the Debian requirement
    """
    comparison = apt_pkg.version_compare(version, required_version)
    
    if required_op == '=':
        return comparison == 0
    elif required_op == '>=':
        return comparison >= 0
    elif required_op == '<=':
        return comparison <= 0
    elif required_op == '>>':
        return comparison > 0
    elif required_op == '<<':
        return comparison < 0
    else:
        return False

def find_min_version(f, filename):

    apt_pkg.init()

    if not os.path.exists(filename):
        logging.error(f"File {filename} does not exist")
        return {}
    data_dict = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
        for e in data_list:
            if e["package"] not in data_dict:
                data_dict[e["package"]] = [e]
            else:
                data_dict[e["package"]].append(e)
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error reading file: {e}")
        return {}
    logging.info(f"Dictionary successfully read from {filename}")
    for v in data_dict.values():
        v.sort(key = lambda x: apt_pkg.version_compare(x['version'], '0'))
    
    for line in f:
        if not requirement:
            continue
        package_name, operator, required_version = parse_requirement_line(line)
 
        for p in data_dict[package_name]:
            if check_version(p['version'], operator, required_version):
                print(p)

def update_debian_metadata_if_newer(base_url, local_base_dir):
    """
    Check if specific Debian metadata files are newer than local ones and update if needed.
    Builds local paths from URL structure.
    Returns True if remote updated, False if no update needed.
    """
    # Specific metadata files to check
    metadata_dirs = [
        # 'db/references.db',
        'db/release.caches.db',
        'indices/files/arch-amd64.files',
        'indices/files/components/source.list.gz'
    ]
    
    # Base local directory
    os.makedirs(local_base_dir, exist_ok=True)
    
    updated = True
    
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
                        logging.info(f"Updating {url_path} (remote is newer)")
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
                                logging.info(f"Extracted to {extract_path}")
                            except Exception as e:
                                 logging.error(f"Error extracting {local_path}: {e}")
                        
                    else:
                        logging.info(f"{url_path} is up to date")
                        updated = False
                else:
                    logging.warning(f"No last-modified header for {url}")
            else:
                # File doesn't exist locally, download it
                logging.info(f"Downloading new file: {url_path}")
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
                        logging.info(f"Extracted to {extract_path}")
                    except Exception as e:
                        logging.error(f"Error extracting {local_path}: {e}")
                
        except requests.RequestException as e:
            logging.error(f"Error processing {url}: {e}")
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
        logging.error(f"Error fetching distributions: {e}")
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
            logging.warning(f"No last-modified header for {url}, forcing download")
            last_modified = "Thu, 01 Jan 1970 00:00:00 GMT"  # Force download
        
        if should_download_file(local_path, last_modified):
            logging.info(f"Downloading: {url}")
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
            logging.info(f"Skipping (up to date): {os.path.basename(local_path)}")
            return False
            
    except requests.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return False

def extract_gz_file(gz_path, output_path):
    """Extract .gz file to output path"""
    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        logging.info(f"Extracted: {os.path.basename(output_path)}")
    except Exception as e:
        logging.error(f"Error extracting {gz_path}: {e}")

def update_debian_metadata(base_url, local_base_dir, components, architectures):
    """Main function to update Debian repository metadata"""

    try:
        os.remove(local_base_dir + "/status")
    except Exception as e:
        pass
    
    logging.info("Fetching distributions list...")
    distributions = get_distributions(base_url + "/dists/")
    
    if not distributions:
        logging.error("No distributions found!")
        return

    logging.info(f"Found {len(distributions)} distributions: {', '.join(distributions)}")
    
    logging.info("Reading existing index...")
    data_dict = read_metadata_index(local_base_dir + "/index.json")

    # Files to download for each distribution
    metadata_files = []
    for arch in architectures:
        if arch == "source":
            metadata_files.append(arch + "/Sources.gz")
        else:
            metadata_files.append(arch + "/Packages.gz")
    
    for dist in distributions:
        logging.info(f"Processing distribution: {dist}")
        dist_url = urljoin(base_url, "dists/" + dist + "/")
        dist_dir = os.path.join(local_base_dir, "dists/" + dist)
        
        for component in components:
            for metadata_file in metadata_files:
                file_path = component + "/" + metadata_file
                # Download .gz file
                remote_url = urljoin(dist_url, file_path)
                local_gz_path = os.path.join(dist_dir, file_path)
                
                if download_file(remote_url, local_gz_path):
                    # Extract the .gz file
                    output_filename = os.path.basename(file_path).replace('.gz', '')
                    output_dir = os.path.dirname(local_gz_path)
                    output_path = os.path.join(output_dir, output_filename)
                    
                    extract_gz_file(local_gz_path, output_path)
                    # Update index dict
                    update_metadata_index(output_path, data_dict, dist, component, metadata_file.split("/")[0])
    
    write_metadata_index(local_base_dir + "/index.json", data_dict)

    with open(local_base_dir + "/status", "w") as f:
        f.write(str(time.time()))

def main():
    """Main entry point"""

    parser = argparse.ArgumentParser(description="Update Debian metadata files from the Debian repository")
    parser.add_argument("--base-url", default="https://ftp.debian.org/debian/", help="Base URL for Debian metadata (default: %(default)s)")
    parser.add_argument("--local-dir", default="./metadata", help="Local directory to store metadata files (default: %(default)s)")
    parser.add_argument("--comp", default=['main'], nargs='+', help="Components main, contrib, non-free, non-free-firmware etc. (default: main)")
    parser.add_argument("--arch", default=['binary-amd64', 'source'], nargs='+', \
        help="Architectures binary-amd64, binary-arm64, source etc. (default: binary-amd64 source)")        
    parser.add_argument("--force", action="store_true", help="Force update even if remote files are older")
    parser.add_argument("--find", action="store_true", help="Read stdin and find a minimum version index packages that satisfies the conditions, format: libpython3.13 (>= 3.13.0~rc3)")
    parser.add_argument("--log-level", default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
        help='set the logging level (default: %(default)s)')    
    
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    if args.find != None:
        find_min_version(sys.stdin, args.local_dir + "/index.json")
        return

    if not update_debian_metadata_if_newer(args.base_url, args.local_dir) and not args.force:
        logging.info("Specific remote metadata files are older, no need to update")
        if os.path.exists(os.path.join(args.local_dir, "status")):
            return

    logging.info("Starting Debian metadata update...")
    update_debian_metadata(args.base_url, args.local_dir, args.comp, args.arch)
    logging.info("Metadata update completed!")

if __name__ == "__main__":
    main()
