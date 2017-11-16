from json import JSONDecoder, JSONEncoder
import aiofiles
from .utils import run_command, Path
import os

decoder = JSONDecoder()
encoder = JSONEncoder()


async def stat_data(path: Path) -> dict:
    """
    only call this on a validated full path
    """
    file_stats = os.stat(path.full_path)
    filename = os.path.basename(path.full_path)
    isFolder = os.path.isdir(path.full_path)
    return {
        'name': filename,
        'path': path.user_path,
        'mtime': int(file_stats.st_mtime*1000),  # given in seconds, want ms
        'size': file_stats.st_size,
        'isFolder': isFolder
    }


async def dir_info(path: Path, show_hidden: bool, query: str = '', recurse=True) -> list:
    """
    only call this on a validated full path
    """
    response = []
    for entry in os.scandir(path.full_path):
        specific_path = Path.from_full_path(entry.path)
        if not show_hidden and entry.name.startswith('.'):
            continue
        if entry.is_dir():
            if query == '' or specific_path.user_path.find(query) != -1:
                response.append(await stat_data(specific_path))
            if recurse:
                response.extend(await dir_info(specific_path, show_hidden, query, recurse))
        elif entry.is_file():
            if query == '' or specific_path.user_path.find(query) != -1:
                response.append(await stat_data(specific_path))
    return response


async def _generate_metadata(path: Path):
    os.makedirs(os.path.dirname(path.metadata_path), exist_ok=True)
    data = {}
    # first ouptut of md5sum is the checksum
    md5 = await run_command('md5sum', path.full_path)
    data['md5'] = md5.split()[0]
    # first output of wc is the count
    lineCount = await run_command('wc', '-l', path.full_path)
    data['lineCount'] = lineCount.split()[0]
    try:  # all things that expect a text file to decode output should be in this block
        data['head'] = await run_command('head', '-10', path.full_path)
        data['tail'] = await run_command('tail', '-10', path.full_path)
    except UnicodeDecodeError as not_text_file:
        data['head'] = 'not text file'
        data['tail'] = 'not text file'
    async with aiofiles.open(path.metadata_path, mode='w') as f:
        await f.writelines(encoder.encode(data))
    return data


async def add_upa(path: Path, UPA: str):
    if os.path.exists(path.metadata_path):
        async with aiofiles.open(path.metadata_path, mode='r') as extant:
            data = await extant.read()
            data = decoder.decode(data)
    else:
        data = await _generate_metadata(path)  # TODO performance optimization
    data['UPA'] = UPA
    async with aiofiles.open(path.metadata_path, mode='w') as update:
        await update.writelines(encoder.encode(data))


async def some_metadata(path: Path, desired_fields=False):
    """
    if desired fields isn't given as a list all fields will be returned
    assumes full_path is valid path to a file
    valid fields for desired_fields are:
    md5, lineCount, head, tail, name, path, mtime, size, isFolder
    """
    file_stats = await stat_data(path)
    if file_stats['isFolder']:
        return file_stats
    if not os.path.exists(path.metadata_path):
        data = await _generate_metadata(path)
    # if metadata older than file: regenerate
    elif os.stat(path.metadata_path).st_mtime < file_stats['mtime']/1000:
        data = await _generate_metadata(path)
    else:  # metadata already exists and is up to date
        async with aiofiles.open(path.metadata_path, mode='r') as f:
            # make metadata fields local variables
            data = await f.read()
            data = decoder.decode(data)
    data = {**data, **file_stats}
    if not desired_fields:
        return data
    result = {}
    for key in desired_fields:
        try:
            result[key] = data[key]
        except KeyError as no_data:
            result[key] = 'error: data not found'  # TODO is this a good way to handle this?
    return result
