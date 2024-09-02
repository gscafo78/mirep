<img src="https://github.com/gscafo78/mirep/blob/main/img/mirrorreplicator.jpeg" alt="Mirror Replicator Logo" width="200" height="200">

Mirror Replicator
====
![Visitor Count](https://visitor-badge.laobi.icu/badge?page_id=gscafo78.mirep)
[![License: GPL](https://img.shields.io/badge/License-GPL-blue.svg)](https://github.com/gscafo78/mirep/blob/main/LICENSE)
![Python Version](https://img.shields.io/badge/Python-3.11.2-blue)


**Mirror Replicator** is a robust script designed to download and create local mirrors of Debian and Ubuntu repositories. This tool ensures reliable and fast access to package updates by maintaining a local copy of the repositories, reducing dependency on external network speeds and availability.

## Features

- **Efficient Synchronization**: Seamlessly syncs Debian-like and Ubuntu-like repositories.
- **Local Mirror Creation**: Facilitates faster package access by creating a local mirror.
- **User-Friendly Configuration**: Easy to set up and use, ideal for developers and system administrators.

## Usage

To use Mirror Replicator, execute the following command:

```bash
$ python3 mirep.py -u <url> -p <protocol> -r <rootpath> -d <distributions> -c <components> -a <architectures> -i <inpath> -t <threads> -v


## Example

To download from `https://deb.debian.org/debian/` to `/var/www/html`, use the command below:


$ python3 mirep.py --proto https --url deb.debian.org --inpath debian --distributions bookworm --components main contrib non-free --architectures amd64 i386 --rootpath /var/www/html
```
After executing this command, the directory `/var/www/html/deb.debian.org/debian/` will contain your mirrored repository.

## Additional Information

- **Contributions**: Contributions are welcome! Please see the [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
- **License**: This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
- **Contact**: For questions or support, please contact [giovanni.scafetta@gmx.com](mailto:giovanni.scafetta@gmx.com).

---