from torch import nn


class ConvBNAct(nn.Module):
    def __init__(
        self, in_channels, out_channels, kernel_size, stride, groups=1, use_act=True
    ):
        super().__init__()
        self.use_act = use_act
        self.conv = nn.Conv2d(
            in_channels,
            out_channels,
            kernel_size,
            stride,
            padding=(kernel_size - 1) // 2,
            groups=groups,
            bias=False,
        )
        self.bn = nn.BatchNorm2d(out_channels)
        if self.use_act:
            self.act = nn.ReLU()

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        if self.use_act:
            x = self.act(x)
        return x

