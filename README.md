# Mechanical Compound Eye
Is a python based Nvidia DeepStream app to watch multiple video streams at once.

## Requirements
- **DeepStream 4.0** (this can be installed on a Tegra platform since JetPack 
4.3 with `sudo apt install deepstream-4.0`)
- [Python bindings for DeepStream](https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/blob/master/HOWTO.md#running-sample-applications)

## Installation
```shell
pip3 install (git url)
```
or
```shell
pip3 install mce
```
or if you don't have pip / don't want to install it
```shell
(git clone this url)
cd mce
python3 ./setup.py install
```

## Example Usage:

To run detections on multiple youtube videos/playlists (requires youtube-dl which can be installed with `pip3 install youtube-dl`):
```mce $(youtube-dl -f best -g https://www.youtube.com/watch?v=pJ5cg83D5AE) $(youtube-dl -f best -g https://www.youtube.com/watch?v=peC1JD9gEKc) $(youtube-dl -f best -g https://www.youtube.com/watch?v=0LYE669fbpU)```

Any uri supported by uridecodebin should work.

## Faq
- **Did you come up with the name?** [No](https://genius.com/Meshuggah-the-demons-name-is-surveillance-lyrics).
- **How can I customize this?** The primary inference config is in ~/.mce/pie.conf

## Known Issues
- tests need to be written
- the decoder spews warning messages... not sure why
- nvinfer doesn't respect batch-engine-file set at runtime for loading a file,
leading to long start times.