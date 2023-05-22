import sys
import os.path
import numpy as np
import array
import torch
import time
import random
import matplotlib.pyplot as plt
from collections import OrderedDict

VERBOSE_STEP = 1000

class BinaryLoader():
    def __init__(self, file, maxStack=10):
        self.File = file

class PlottingWindow():
    def __init__(self, title, min=None, max=None, cumulativeHorizon=100, drawInterval=100):
        plt.ion()
        self.Figure, self.Axes = plt.subplots()
        self.Title = title
        self.CumulativeHorizon = cumulativeHorizon
        self.DrawInterval = drawInterval
        self.YMin = min
        self.YMax = max
        self.YRange = [sys.float_info.max if min==None else min, sys.float_info.min if max==None else max]
        self.Functions = {} #string->[History, Horizon]
        self.Counter = 0

    def Add(self, *args): #arg->(value, label)
        for arg in args:
            value = arg[0]
            label = arg[1]
            if label not in self.Functions:
                self.Functions[label] = ([],[])
            function = self.Functions[label]
            function[0].append(value)
            function[1].append(sum(function[0][-self.CumulativeHorizon:]) / len(function[0][-self.CumulativeHorizon:]))

            self.YRange[0] = min(self.YRange[0], value) if self.YMin==None else self.YRange[0]
            self.YRange[1] = max(self.YRange[1], value) if self.YMax==None else self.YRange[1]

        self.Counter += 1
        if self.Counter >= self.DrawInterval:
            self.Counter = 0
            self.Draw()

    def Draw(self):
        self.Axes.cla()
        self.Axes.set_title(self.Title)
        for label in self.Functions.keys():
            function = self.Functions[label]
            step = max(int(len(function[0])/self.DrawInterval), 1)
            self.Axes.plot(function[0][::step], label=label + " (" + str(round(self.CumulativeValue(label), 3)) + ")")
            self.Axes.plot(function[1][::step], c=(0,0,0))
        self.Axes.set_ylim(self.YRange[0], self.YRange[1])
        self.Axes.legend()
        plt.gcf().canvas.draw_idle()
        plt.gcf().canvas.start_event_loop(1e-5)

    def Value(self, label=None):
        if label==None:
            return sum(x[0][-1] for x in self.Functions.values())
        else:
            return self.Functions[label][0][-1]

    def CumulativeValue(self, label=None):
        if label==None:
            return sum(x[1][-1] for x in self.Functions.values())
        else:
            return self.Functions[label][1][-1]

def SetSeed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True

def Timestamp():
    return time.time()

def ElapsedTime(timestamp, output=False, formatted=False):
    elapsed = 1000 * (time.time() - timestamp) #milliseconds
    if output:
        print("{0:.3f}".format(elapsed), 'ms')
    if formatted:
        return "{0:.3f}".format(elapsed) + ' ms'
    else:
        return elapsed


def CollectPointers(file, max=None):
    pointers = []
    with open(file) as f:
        pivot = 0
        while(f.readline()):
            pointers.append(pivot)
            pivot = f.tell()
            if len(pointers) % VERBOSE_STEP == 0:
                print('Collecting data pointers for ' + file + ' - ' + str(len(pointers)), end="\r")
            if max != None and len(pointers) == max:
                break
    print("")
    # print("Loaded " + file)
    return np.array(pointers)

def ReadChunk(file, pointers):
    data = []
    with open(file) as f:
        for i in pointers:
            f.seek(i)
            data.append(np.float32(np.fromstring(f.readline(), sep=' ')))
    return np.concatenate(data).reshape(len(pointers), -1)

#binaryFile = .bin data matrix of shape samples x features
#sampleCount = number of samples in the file
#featureCount = number of features per sample
def ReadBinary(binaryFile, sampleCount, featureCount):
    bytesPerLine = featureCount*4
    data = []
    with open(binaryFile, "rb") as f:
        for i in np.arange(sampleCount):
            if i % max(int(sampleCount / VERBOSE_STEP),1) == 0:
                print('Reading binary ' + binaryFile + '...', round(100 * i / sampleCount, 2), "%", end="\r")
            f.seek(i*bytesPerLine)
            bytes = f.read(bytesPerLine)
            data.append(np.float32(array.array('f', bytes)))
    print('Reading binary ' + binaryFile + '...', 100, "%", end="\r")
    print("")
    return np.concatenate(data).reshape(sampleCount, -1)
    # Example:
    # samples = 100
    # features = 2904
    # batch = ReadAll("Input.bin", samples, features)

#binaryFile = .bin data matrix of shape samples x features
#sampleIndices = list of sample indices from 0
#featureCount = number of features per sample
def ReadBatch(binaryFile, sampleIndices, featureCount):
    bytesPerLine = featureCount*4
    data = []
    with open(binaryFile, "rb") as f:
        for i in sampleIndices:
            f.seek(i*bytesPerLine)
            bytes = f.read(bytesPerLine)
            data.append(np.float32(array.array('f', bytes)))
    return np.concatenate(data).reshape(len(sampleIndices), -1)
    # Example:
    # batchSize = 32
    # samples = 100
    # features = 2904
    # batch = ReadBatch("Input.bin", np.random.randint(samples, size=batchSize), features)

def SaveONNX(path, model, input_size, input_names, output_names):
    FromDevice(model)
    torch.onnx.export(
        model,                            # model being run
        torch.randn(1, input_size),          # model input (or a tuple for multiple inputs)
        path,            # where to save the model (can be a file or file-like object)
        training=False,
        export_params=True,                 # store the trained parameter weights inside the model file
        opset_version=9,                    # the ONNX version to export the model to
        do_constant_folding=False,          # whether to execute constant folding for optimization
        input_names = input_names,                # the model's input names
        output_names = output_names                # the model's output names
    )
    ToDevice(model)

def ReadNorm(file):
    N = np.float32(np.loadtxt(file))
    N[1, N[1, :] == 0] = 1
    return N
    
def LoadNormalization(path, dim, debug=False):
    norm = np.fromfile(path, dtype=np.float32)
    if(debug):
        print("Loaded " + path)
    return norm.reshape(2, dim)

def MakeDirectory(path):
    if not os.path.exists(path):
        os.mkdir(path)

def ToDevice(x):
    return x.cuda() if torch.cuda.is_available() else x

def FromDevice(x):
    return x.cpu() if torch.cuda.is_available() else x

def ToNumpy(X):
    return X.data.cpu().numpy()

# def SaveBinary(X, folder, name, debug=False):
#     if len(X.shape) == 3:
#         if(X.shape[0] == 1):
#             path = folder + "/" + name + ".bin"
#             X[0].tofile(path)
#             if(debug):
#                 print("Saved " + path)
#         else:
#             for i in range(X.shape[0]):
#                 path = folder + "/" + name + "_" + str(i+1) + ".bin"
#                 X[i].tofile(path)
#                 if(debug):
#                     print("Saved " + path)
#     else:
#         path = folder + "/" + name + ".bin"
#         X.tofile(path)
#         if(debug):
#             print("Saved " + path)

def LoadTxtRaw(path, debug=False):
    with open(path) as f:
        content = f.read()
        content1D = content.split("\n")
        content2D = [entry.split(" ") for entry in content1D]
    if(debug):
        print("Loaded "+ path)
    return content2D

def Transpose2DList(values):
    return [list(i) for i in zip(*values)]

def LoadTxtAsInt(path, debug=False):
    txt = np.loadtxt(path, dtype=np.int64)
    if(debug):
        print("Loaded " + path)
    return txt

def LoadTxtAsFloat(path, debug=False):
    txt = np.loadtxt(path, dtype=np.float32)
    if(debug):
        print("Loaded " + path)
    return txt

def LoadTxt(path, debug=False):
    txt = np.float32(np.loadtxt(path))
    if(debug):
        print("Loaded " + path)
    return txt

# def Normalize(X, mean, std):
#     return (X - mean) / std

# def Renormalize(X, mean, std):
#     return (X * std) + mean

def Normalize(X, N):
    mean = N[0]
    std = N[1]
    return (X - mean) / std

def Renormalize(X, N):
    mean = N[0]
    std = N[1]
    return (X * std) + mean

def FreezeWeights(model, names, value):
    for name, param in model.named_parameters():
        if name in names:
            param.requires_grad = not value

def GetStateDict(model, names):
    dict = OrderedDict()
    for param_tensor in model.state_dict():
        if param_tensor in names :
            dict[param_tensor] = model.state_dict()[param_tensor]
    return dict

def PrintStateDict(model):
    for param_tensor in model.state_dict():
        print(param_tensor, "\t", model.state_dict()[param_tensor].size())

def PrintParameters(model, learnable=True):
    if learnable:
        print("Learnable Parameters:")
    else:
        print("Static Parameters")
    for name, param in model.named_parameters():
        if learnable:
            if param.requires_grad:
                print(name)
        else:
            if not param.requires_grad:
                print(name)

def GetParameters(model, learnable=True):
    params = []
    for name, param in model.named_parameters():
        if learnable:
            if param.requires_grad:
                params.append(param)
        else:
            if not param.requires_grad:
                params.append(param)
    return params

def CountParameters(model, learnable=True):
    if learnable:
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    else:
        return sum(p.numel() for p in model.parameters() if not p.requires_grad)

def Gaussian(N, std, sym=True):
    if N < 1:
        return np.array([])
    if N == 1:
        return np.ones(1, 'd')
    odd = N % 2
    if not sym and not odd:
        N = N + 1
    n = np.arange(0, N) - (N - 1.0) / 2.0
    sig2 = 2 * std * std
    w = np.exp(-n ** 2 / sig2)
    if not sym and not odd:
        w = w[:-1]
    return w

def GMSELoss():
    def fn(output, target):
        filter = ToDevice(torch.tensor(Gaussian(26*121, 26*121/6.0), requires_grad=True))
        filter = filter.unsqueeze(0)
        loss = torch.mean(filter * (output - target)**2)
        return loss
    return fn

def Rescale(value, valueMin, valueMax, resultMin, resultMax):
    if valueMax-valueMin != 0.0:
        return (value-valueMin)/(valueMax-valueMin)*(resultMax-resultMin) + resultMin
    else:
        return value

def RainbowColor(index, count):
    frequency = 5.0/count
    return (
        Rescale(np.sin(frequency*index + 0.0) * (127.0) + 128.0, 0.0, 255.0, 0.0, 1.0),
        Rescale(np.sin(frequency*index + 2.0) * (127.0) + 128.0, 0.0, 255.0, 0.0, 1.0),
        Rescale(np.sin(frequency*index + 4.0) * (127.0) + 128.0, 0.0, 255.0, 0.0, 1.0),
        1.0
    )

# def Gaussian_Noise(x, std, dims=None):
#     if std==0:
#         return x
#     elif dims==None:
#         return x + np.random.normal(0.0, std, (x.shape[0], x.shape[1])).astype(np.float32)
#     else:
#         noise = np.zeros((x.shape[0], x.shape[1]),dtype=np.float32)
#         noise[:,dims] = np.random.normal(0.0, std, (x.shape[0], len(dims))).astype(np.float32)
#         return x + noise

# def ScaleLoss(sub, scale):
#     if scale:
#         scale = np.array(scale)
#         if(len(scale.shape)<2):
#             scale = np.expand_dims(scale, 0)
#             scale = tf.constant(scale, dtype=tf.float32)
#             return sub*scale
#     else:
#         return sub

# def CollectPointers(file, max=None):
#     pointers = []
#     with open(file) as f:
#         pivot = 0
#         while(f.readline()):
#             pointers.append(pivot)
#             pivot = f.tell()
#             if len(pointers) % VERBOSE_STEP == 0:
#                 print('Collecting data pointers for ' + file + ' - ' + str(len(pointers)), end="\r")
#             if max != None and len(pointers) == max:
#                 break
#     print("")
#     # print("Loaded " + file)
#     return np.array(pointers)

# def ReadChunk(file, pointers):
#     data = []
#     with open(file) as f:
#         for i in pointers:
#             f.seek(i)
#             data.append(np.float32(np.fromstring(f.readline(), sep=' ')))
#     return np.concatenate(data).reshape(len(pointers), -1)
