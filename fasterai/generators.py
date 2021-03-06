from fasterai.modules import *
from abc import ABC, abstractmethod

class GeneratorModule(ABC, nn.Module):
    def __init__(self):
        super().__init__()
    
    def set_trainable(self, trainable: bool):
        set_trainable(self, trainable)

    @abstractmethod
    def get_layer_groups(self, precompute: bool = False)->[]:
        pass

    def freeze_to(self, n):
        c=self.get_layer_groups()
        for l in c:     set_trainable(l, False)
        for l in c[n:]: set_trainable(l, True)

 
class Unet34(GeneratorModule): 
    def __init__(self, nf_factor:int=1, scale:int=1):
        super().__init__()
        assert (math.log(scale,2)).is_integer()
        leakyReLu=False
        self_attention=True
        bn=True
        sn=True
        self.rn, self.lr_cut = get_pretrained_resnet_base()
        self.sfs = [SaveFeatures(self.rn[i]) for i in [2,4,5,6]]

        self.up1 = UnetBlock(512,256,512*nf_factor, sn=sn, leakyReLu=leakyReLu, bn=bn)
        self.up2 = UnetBlock(512*nf_factor,128,512*nf_factor, sn=sn, leakyReLu=leakyReLu, bn=bn)
        self.up3 = UnetBlock(512*nf_factor,64,512*nf_factor, sn=sn, self_attention=self_attention, leakyReLu=leakyReLu, bn=bn)
        self.up4 = UnetBlock(512*nf_factor,64,256*nf_factor, sn=sn, leakyReLu=leakyReLu, bn=bn)
        self.up5 = UpSampleBlock(256*nf_factor, 32*nf_factor, 2*scale, sn=sn, leakyReLu=leakyReLu, bn=bn) 
        self.out= nn.Sequential(ConvBlock(32*nf_factor, 3, ks=3, actn=False, bn=False, sn=sn), nn.Tanh())

    #Gets around irritating inconsistent halving come from resnet
    def _pad_xtensor(self, x, target):
        h = x.shape[2] 
        w = x.shape[3]

        target_h = target.shape[2]*2
        target_w = target.shape[3]*2

        if h<target_h or w<target_w:
            target = Variable(torch.zeros(x.shape[0], x.shape[1], target_h, target_w))
            target[:,:,:h,:w]=x
            return to_gpu(target)

        return x
           
    def forward(self, x_in: torch.Tensor):
        x = F.relu(self.rn(x_in))
        x = self.up1(x, self._pad_xtensor(self.sfs[3].features, x))
        x = self.up2(x, self._pad_xtensor(self.sfs[2].features, x))
        x = self.up3(x, self._pad_xtensor(self.sfs[1].features, x))
        x = self.up4(x, self._pad_xtensor(self.sfs[0].features, x))
        x = self.up5(x)
        x = self.out(x)
        return x
    
    def get_layer_groups(self, precompute: bool = False)->[]:
        lgs = list(split_by_idxs(children(self.rn), [self.lr_cut]))
        return lgs + [children(self)[1:]]
    
    def close(self):
        for sf in self.sfs: 
            sf.remove()

class LearnerGenModuleWrapper():
    def __init__(self, model: GeneratorModule, name:str):
        self.model = to_gpu(model)
        self.name = name

    def get_layer_groups(self, precompute):
        return self.model.get_layer_groups()