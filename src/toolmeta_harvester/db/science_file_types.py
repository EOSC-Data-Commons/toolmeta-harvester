import re

EXT_PATTERN = re.compile(r"\.\w+(?:\.\w+)*")

FILE_TYPES = {
    # --- Core scientific ---
    "mat": ".mat",
    "hdf5": ".h5",
    "hdf": ".hdf",
    "h5": ".h5",
    "netcdf": ".nc",
    "cdf": ".cdf",
    "zarr": ".zarr",
    "root": ".root",

    # --- Tabular / data science ---
    "csv": ".csv",
    "tsv": ".tsv",
    "parquet": ".parquet",
    "feather": ".feather",
    "arrow": ".arrow",
    "json": ".json",
    "xml": ".xml",
    "yaml": ".yaml",
    "yml": ".yaml",

    # --- Statistics / scientific computing ---
    "rds": ".rds",
    "rdata": ".rdata",
    "stata": ".dta",
    "spss": ".sav",
    "pickle": ".pkl",
    "pkl": ".pkl",
    "numpy": ".npy",
    "npz": ".npz",

    # --- Astronomy ---
    "fits": ".fits",
    "fit": ".fits",
    "votable": ".vot",

    # --- Medical imaging ---
    "dicom": ".dcm",
    "dcm": ".dcm",
    "nifti": ".nii",
    "nii": ".nii",
    "nii.gz": ".nii.gz",
    "analyze": ".img",
    "mgh": ".mgh",
    "mgz": ".mgz",

    # --- Bioinformatics / genomics ---
    "fasta": ".fasta",
    "fa": ".fasta",
    "fna": ".fasta",
    "faa": ".fasta",
    "fastq": ".fastq",
    "sam": ".sam",
    "bam": ".bam",
    "cram": ".cram",
    "vcf": ".vcf",
    "bcf": ".bcf",
    "gff": ".gff",
    "gff3": ".gff3",
    "gtf": ".gtf",
    "bed": ".bed",
    "pdb": ".pdb",

    # --- Chemistry / materials ---
    "mol": ".mol",
    "sdf": ".sdf",
    "cml": ".cml",
    "xyz": ".xyz",
    "cif": ".cif",
    "jcamp": ".jdx",
    "jdx": ".jdx",

    # --- Geospatial / earth science ---
    "grib": ".grib",
    "grb": ".grib",
    "bufr": ".bufr",
    "geotiff": ".tiff",
    "tiff": ".tiff",
    "tif": ".tiff",
    "shapefile": ".shp",
    "shp": ".shp",
    "kml": ".kml",
    "kmz": ".kmz",
    "las": ".las",
    "laz": ".laz",
    "dem": ".dem",
    "asc": ".asc",

    # --- Microscopy / imaging ---
    "ome-tiff": ".ome.tiff",
    "ometiff": ".ome.tiff",
    "lsm": ".lsm",
    "czi": ".czi",
    "nd2": ".nd2",
    "mrc": ".mrc",
    "ccp4": ".ccp4",

    # --- Signals / neuroscience ---
    "edf": ".edf",
    "bdf": ".bdf",
    "gdf": ".gdf",
    "tool.b": ".tool.b",
    "xdf": ".xdf",

    # --- Engineering / simulation ---
    "vtk": ".vtk",
    "cgns": ".cgns",
    "exodus": ".exo",
    "exo": ".exo",
    "ensight": ".case",
    "case": ".case",
    "nexus": ".nxs",
    "nxs": ".nxs",

    # --- Generic scientific ---
    "dat": ".dat",
    "txt": ".txt",

    # --- Archives (often used for datasets) ---
    "zip": ".zip",
    "tar": ".tar",
    "tar.gz": ".tar.gz",

    # --- Images (common in scientific contexts) ---
    "png": ".png",
    "jpg": ".jpg",
    "jpeg": ".jpeg",
    "bmp": ".bmp",
    "gif": ".gif",
    "svg": ".svg",
    "pdf": ".pdf",
    "eps": ".eps",
    "ps": ".ps",

    # --- Code / scripts (often shared in scientific projects) ---
    "py": ".py",
    "r": ".r",
    "m": ".m",
    "ipynb": ".ipynb",
    "jl": ".jl",
    "sh": ".sh",
    "bash": ".sh",
    "zsh": ".sh",
    "csh": ".sh",
    "cpp": ".cpp",
    "java": ".java",
    "js": ".js",

}

EXTENSIONS = set(FILE_TYPES.values())

def extract_filetypes(text):
    text_lower = text.lower()
    
    found = set()
    
    # --- (1) explicit extensions ---
    for ext in EXT_PATTERN.findall(text_lower):
        if ext in EXTENSIONS:
            found.add(ext)
    
    # --- (2) word-based lookup ---
    words = re.findall(r"\b[\w\-\.]+\b", text_lower)
    
    for w in words:
        # direct match
        if w in FILE_TYPES:
            found.add(FILE_TYPES[w])
        
        # normalise hyphen variants (e.g. ome-tiff → ometiff)
        w_norm = w.replace("-", "")
        if w_norm in FILE_TYPES:
            found.add(FILE_TYPES[w_norm])

    return sorted(ext.lstrip(".") for ext in found)
