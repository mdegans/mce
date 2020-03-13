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
## Faq
- **Did you come up with the name?** [No](https://genius.com/Meshuggah-the-demons-name-is-surveillance-lyrics).

## Known Issues
- half the tests fail. they need to be rewritten
- the decoder spews warning messages... not sure why
