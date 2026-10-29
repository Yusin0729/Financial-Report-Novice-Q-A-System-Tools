from torch import nn


from ..common import Activation


class ConvBNLayer(nn.Module):
    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size,
        stride,
        padding,
        groups=1,
        if_act=True,
        act=None,
        name=None,
    ):
        super(ConvBNLayer, self).__init__()
        self.if_act = if_act
        self.conv = nn.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            groups=groups,
            bias=False,
        )

        self.bn = nn.BatchNorm2d(
            out_channels,
        )
        if self.if_act:
            self.act = Activation(act_type=act, inplace=True)

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        if self.if_act:
            x = self.act(x)
        return x


class SEModule(nn.Module):
    def __init__(self, in_channels, reduction=4, name=""):
        super(SEModule, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.conv1 = nn.Conv2d(
            in_channels=in_channels,
            out_channels=in_channels // reduction,
            kernel_size=1,
            stride=1,
            padding=0,
            bias=True,
        )
        self.relu1 = Activation(act_type="relu", inplace=True)
        self.conv2 = nn.Conv2d(
            in_channels=in_channels // reduction,
            out_channels=in_channels,
            kernel_size=1,
            stride=1,
            padding=0,
            bias=True,
        )
        self.hard_sigmoid = Activation(act_type="hard_sigmoid", inplace=True)

    def forward(self, inputs):
        outputs = self.avg_pool(inputs)
        outputs = self.conv1(outputs)
        outputs = self.relu1(outputs)
        outputs = self.conv2(outputs)
        outputs = self.hard_sigmoid(outputs)
        outputs = inputs * outputs
        return outputs

