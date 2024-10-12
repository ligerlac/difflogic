import torch
import numpy as np

BITS_TO_NP_DTYPE = {8: np.int8, 16: np.int16, 32: np.int32, 64: np.int64}


# | id | Operator             | AB=00 | AB=01 | AB=10 | AB=11 |
# |----|----------------------|-------|-------|-------|-------|
# | 0  | 0                    | 0     | 0     | 0     | 0     |
# | 1  | A and B              | 0     | 0     | 0     | 1     |
# | 2  | not(A implies B)     | 0     | 0     | 1     | 0     |
# | 3  | A                    | 0     | 0     | 1     | 1     |
# | 4  | not(B implies A)     | 0     | 1     | 0     | 0     |
# | 5  | B                    | 0     | 1     | 0     | 1     |
# | 6  | A xor B              | 0     | 1     | 1     | 0     |
# | 7  | A or B               | 0     | 1     | 1     | 1     |
# | 8  | not(A or B)          | 1     | 0     | 0     | 0     |
# | 9  | not(A xor B)         | 1     | 0     | 0     | 1     |
# | 10 | not(B)               | 1     | 0     | 1     | 0     |
# | 11 | B implies A          | 1     | 0     | 1     | 1     |
# | 12 | not(A)               | 1     | 1     | 0     | 0     |
# | 13 | A implies B          | 1     | 1     | 0     | 1     |
# | 14 | not(A and B)         | 1     | 1     | 1     | 0     |
# | 15 | 1                    | 1     | 1     | 1     | 1     |


ID_TO_OP = {
    0 : lambda a,b: torch.zeros_like(a),
    1 : lambda a,b: a * b,
    2 : lambda a,b: a - a * b,
    3 : lambda a,b: a,
    4 : lambda a,b: b - a * b,
    5 : lambda a,b: b,
    6 : lambda a,b: a + b - 2 * a * b,
    7 : lambda a,b: a + b - a * b,
    8 : lambda a,b: 1 - (a + b - a * b),
    9 : lambda a,b: 1 - (a + b - 2 * a * b),
    10: lambda a,b: 1 - b,
    11: lambda a,b: 1 - b + a * b,
    12: lambda a,b: 1 - a,
    13: lambda a,b: 1 - a + a * b,
    14: lambda a,b: 1 - a + a * b,
    15: lambda a,b: 1 - a * b,
}


def bin_op(a, b, i):
    assert a[0].shape == b[0].shape, (a[0].shape, b[0].shape)
    if a.shape[0] > 1:
        assert a[1].shape == b[1].shape, (a[1].shape, b[1].shape)
    return ID_TO_OP[i](a, b)


def bin_op_s(a, b, i_s):
    r = torch.zeros_like(a)
    for i in range(16):
        u = bin_op(a, b, i)
        r = r + i_s[..., i] * u
    return r


########################################################################################################################


def get_unique_connections(in_dim, out_dim, device='cuda'):
    assert out_dim * 2 >= in_dim, 'The number of neurons ({}) must not be smaller than half of the number of inputs ' \
                                  '({}) because otherwise not all inputs could be used or considered.'.format(
        out_dim, in_dim
    )

    x = torch.arange(in_dim).long().unsqueeze(0)

    # Take pairs (0, 1), (2, 3), (4, 5), ...
    a, b = x[..., ::2], x[..., 1::2]
    if a.shape[-1] != b.shape[-1]:
        m = min(a.shape[-1], b.shape[-1])
        a = a[..., :m]
        b = b[..., :m]

    # If this was not enough, take pairs (1, 2), (3, 4), (5, 6), ...
    if a.shape[-1] < out_dim:
        a_, b_ = x[..., 1::2], x[..., 2::2]
        a = torch.cat([a, a_], dim=-1)
        b = torch.cat([b, b_], dim=-1)
        if a.shape[-1] != b.shape[-1]:
            m = min(a.shape[-1], b.shape[-1])
            a = a[..., :m]
            b = b[..., :m]

    # If this was not enough, take pairs with offsets >= 2:
    offset = 2
    while out_dim > a.shape[-1] > offset:
        a_, b_ = x[..., :-offset], x[..., offset:]
        a = torch.cat([a, a_], dim=-1)
        b = torch.cat([b, b_], dim=-1)
        offset += 1
        assert a.shape[-1] == b.shape[-1], (a.shape[-1], b.shape[-1])

    if a.shape[-1] >= out_dim:
        a = a[..., :out_dim]
        b = b[..., :out_dim]
    else:
        assert False, (a.shape[-1], offset, out_dim)

    perm = torch.randperm(out_dim)

    a = a[:, perm].squeeze(0)
    b = b[:, perm].squeeze(0)

    a, b = a.to(torch.int64), b.to(torch.int64)
    a, b = a.to(device), b.to(device)
    a, b = a.contiguous(), b.contiguous()
    return a, b


########################################################################################################################


class GradFactor(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, f):
        ctx.f = f
        return x

    @staticmethod
    def backward(ctx, grad_y):
        return grad_y * ctx.f, None


########################################################################################################################



