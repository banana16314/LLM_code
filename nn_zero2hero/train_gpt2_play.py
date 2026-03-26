from dataclasses import dataclass
import torch
import torch.nn as nn
from torch.nn import functional as F
import math
class CausalSelfAttention(nn.Module):

    def __init__(self, config):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        # key, query, value projections for all heads, but in a batch
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd)
        # output projection
        self.c_proj = nn.Linear(config.n_embd, config.n_embd)
        self.c_proj.NANOGPT_SCALE_INIT = 1
        # regularization
        self.n_head = config.n_head
        self.n_embd = config.n_embd

    def forward(self, x):
        B, T, C = x.size() # batch size, sequence length, embedding dimensionality (n_embd)
        # calculate query, key, values for all heads in batch and move head forward to be the batch dim
        # nh is "number of heads", hs is "head size", and C (number of channels) = nh * hs
        # e.g. in GPT-2 (124M), n_head=12, hs=64, so nh*hs=C=768 channels in the Transformer
        qkv = self.c_attn(x)
        q, k, v = qkv.split(self.n_embd, dim=2)
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)

        # 原始attn计算
        # large(T, T) matrix for all the queries and keyes
        # att = (q @k.transpose(-2,-1))*(1.0/math.sqrt(k.szie(-1)))
        # att = att.masked_fill(self.bias[:,:,:T,:T] == 0, float('inf'))
        # att = F.softmax(att, dim=1)
        # y = att@v # (B, nh, T, T) x (B, nh, T, hs) -> (B, nh, T, hs)

        y = F.scaled_dot_product_attention(q, k, v, is_causal=True) # flash attention

        y = y.transpose(1, 2).contiguous().view(B, T, C) # re-assemble all head outputs side by side
        # output projection
        y = self.c_proj(y)
        return y


class MLP(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd) # 两层线性层，尺寸先扩大4倍再映射回去
        self.gelu = nn.GELU(approximate="tanh")
        self.c_proj = nn.Linear(4*config.n_embd, config.n_embd)

    def forward(self, x):
        x = self.c_fc(x)
        x = self.gelu(x)
        x = self.c_proj(x)
        return x

class Block(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.ln_1 = nn.LayerNorm(config.n_embd)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = nn.LayerNorm(config.n_embd)
        self.mlp = MLP(config) # you can call this layer "ffn"

    def forward(self, x):
        # 此处两次残差连接，计算缩放因子是 2* n_layer
        x = x + self.attn(self.ln_1(x)) # tokens communicate with each other, reduce(规约)/aggregation function/pooling function/weighted sum function
        x = x + self.mlp(self.ln_2(x)) # 操作单个token，进行映射MAP，对已汇集的信息进行think和representation 
        return x


@dataclass
class GPTConfig:
    block_size: int = 1024 # max sequence length
    vocab_size: int = 50257 # number of tokens: 50,000 BPE merges + 256 bytes tokens + 1 <|endoftext|> token
    n_layer: int = 12 # number of layers
    n_head: int = 12 # number of heads
    n_embd: int = 768 # embedding dimension

class GPT(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.config = config

        self.transformer = nn.ModuleDict(dict(
            wte = nn.Embedding(config.vocab_size, config.n_embd), # weights token embding
            wpe = nn.Embedding(config.block_size, config.n_embd), # weights pos embding
            h = nn.ModuleList([Block(config) for _ in range(config.n_layer)]), # h0...h11
            ln_f = nn.LayerNorm(config.n_embd), # layerNorm for final layer
        ))
        # final classifier, head, (final peojectiong layer),project from 768 to vocab size
        # 50257 * 768
        # 最后会将768扩展为50257，以便得到下一个token的logits，然后将logits经过softmax变成概率，再采样得到输出
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False) 

        ## weight sharing scheme
        self.transformer.wte.weight = self.lm_head.weight

        # init params
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            std = 0.02
            if hasattr(module, 'NANOGPT_SCALE_INIT'):
                # 对应Block的两次残差连接，计算缩放因子是 2* n_layer
                std *= (2 * self.config.n_layer) ** -0.5
            torch.nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx, targets=None):
        # idx is of shape (B, T)
        # batch, T tokens in a sequence
        B, T = idx.size()
        # T cannot be more than block size(seq length)
        assert T <= self.config.block_size, f"Cannot forward sequence of length {T}, block size is only {self.config.block_size}"
        # forward the token and posisition embeddings
        pos = torch.arange(0, T, dtype=torch.long, device=idx.device) # shape (T)
        pos_emb = self.transformer.wpe(pos) # position embeddings of shape (T, n_embd)
        tok_emb = self.transformer.wte(idx) # token embeddings of shape (B, T, n_embd)
        x = tok_emb + pos_emb
        # forward the blocks of the transformer
        for block in self.transformer.h:
            x = block(x)
        # forward the final layernorm and the classifier
        x = self.transformer.ln_f(x)
        logits = self.lm_head(x) # (B, T, vocab_size)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss

    @classmethod
    def from_pretrained(cls, model_type):
        """Loads pretrained GPT-2 model weights from huggingface"""
        assert model_type in {'openai-community/gpt2', 'gpt2-medium', 'gpt2-large', 'gpt2-xl'}
        from transformers import GPT2LMHeadModel
        print("loading weights from pretrained gpt: %s" % model_type)

        # n_layer, n_head and n_embd are determined from model_type
        config_args = {
            'openai-community/gpt2':         dict(n_layer=12, n_head=12, n_embd=768),  # 124M params
            'gpt2-medium':  dict(n_layer=24, n_head=16, n_embd=1024), # 350M params
            'gpt2-large':   dict(n_layer=36, n_head=20, n_embd=1280), # 774M params
            'gpt2-xl':      dict(n_layer=48, n_head=25, n_embd=1600), # 1558M params
        }[model_type]
        config_args['vocab_size'] = 50257 # always 50257 for GPT model checkpoints
        config_args['block_size'] = 1024 # always 1024 for GPT model checkpoints
        # create a from-scratch initialized minGPT model
        config = GPTConfig(**config_args)
        model = GPT(config)
        sd = model.state_dict()
        sd_keys = sd.keys()
        sd_keys = [k for k in sd_keys if not k.endswith('.attn.bias')] # discard this mask / buffer, not a param

        # init a huggingface/transformers model
        model_hf = GPT2LMHeadModel.from_pretrained(model_type)
        sd_hf = model_hf.state_dict()

        # copy while ensuring all of the parameters are aligned and match in names and shapes
        sd_keys_hf = sd_hf.keys()
        sd_keys_hf = [k for k in sd_keys_hf if not k.endswith('.attn.masked_bias')] # ignore these, just a buffer
        sd_keys_hf = [k for k in sd_keys_hf if not k.endswith('.attn.bias')] # same, just the mask (buffer)
        transposed = ['attn.c_attn.weight', 'attn.c_proj.weight', 'mlp.c_fc.weight', 'mlp.c_proj.weight']
        # basically the openai checkpoints use a "Conv1D" module, but we only want to use a vanilla Linear
        # this means that we have to transpose these weights when we import them
        assert len(sd_keys_hf) == len(sd_keys), f"mismatched keys: {len(sd_keys_hf)} != {len(sd_keys)}"
        for k in sd_keys_hf:
            if any(k.endswith(w) for w in transposed):
                # special treatment for the Conv1D weights we need to transpose
                assert sd_hf[k].shape[::-1] == sd[k].shape
                with torch.no_grad():
                    sd[k].copy_(sd_hf[k].t())
            else:
                # vanilla copy over the other parameters
                assert sd_hf[k].shape == sd[k].shape
                with torch.no_grad():
                    sd[k].copy_(sd_hf[k])

        return model


###----------------------------------------------
# model = GPT.from_pretrained('openai-community/gpt2')
# did not crash yay!
# > Hello, I`m a language model,  which is very important in the  translation  and has to be supported.
# I
# > Hello, I`m a language model, ~~ and I am writing a language model. ~~ It`s going to take more time than
# > Hello, I`m a language model,  with two of them.  So, as I said above, it's really easy to
# > Hello, I`m a language model, !!! You might say "Why are you so angry?", !!! If you say we didn`t
# > Hello, I`m a language model, _________. I wrote with _________. I thought _________. We know how _________. 


model = GPT(GPTConfig())
# did not crash yay!
# > Hello, I`m a language model,  commanded Example SET replen Clint follows Sort easily enactmentUNartisanlatesticals nutrit escal assetNPR McKenzie mast526
# > Hello, I`m a language model,  Clifford Par snatcholar skew executesebus functionality Nolan Hoo generous dropsicer utilizing bowlsugar 1997GD sinners au
# > Hello, I`m a language model,  Illuminati dens Dig starting Mansion Laden HumeissionPassword Maple dronepractographersIANapologizardsemark Plug mast dozen
# > Hello, I`m a language model,  Kro reflective#$ince RISBU subsidy weed cheaper Manilasouth biologist Author hesitationMother Acadulence timestamp Basically training
# > Hello, I`m a language model,  Clifford Particip)</kAx RobbieALSE Nguyenylestraumatic Presidentsonga sear click lapt tupleLoading 427 RAragon

print('did not crash yay!')

model.eval()
model.to("cuda")

num_return_sequences = 5
max_length = 30

import tiktoken
enc = tiktoken.get_encoding('gpt2')


tokens = enc.encode('Hello, I`m a language model, ')
tokens = torch.tensor(tokens, dtype=torch.long) # 8 tokens
tokens = tokens.unsqueeze(0).repeat(num_return_sequences, 1) # (5, 8)
x= tokens.to("cuda")

# generate!
while x.size(1) < max_length: # max_length=30
    # forward the model to get the logits
    with torch.no_grad():
        logits = model(x)[0] # (B, T, vocab_size)
        # take the logits at the last position
        logits = logits[:, -1, :] # (B, vocab_size)
        # get the probabilities
        probs = F.softmax(logits, dim=-1)
        # do top-k sampling of 50 (huggingface pipeline default)
        # topk_probs here becomes (5, 50), topk_indices is (5, 50)
        topk_probs, topk_indices = torch.topk(probs, 50, dim=-1)
        # select a token from the top-k probabilities
        # note: multinomial does not demand the input to sum to 1
        ix = torch.multinomial(topk_probs, 1) # (B, 1)
        # gather the corresponding indices
        xcol = torch.gather(topk_indices, -1, ix) # (B, 1)
        # append to the sequence
        x = torch.cat((x, xcol), dim=1)


for i in range(num_return_sequences):
    tokens = x[i, :max_length].tolist()
    decoded = enc.decode(tokens)
    print(">", decoded)


# wc input.txt
# 40000  202651 1115394 input.txt
# 40000 lines, 202651 words, 1115394 bytes

# 极为简单的数据集，方便我们调试

with open('input.txt', 'r') as f:
    text = f.read()
data = text[:1000] # first 1,000 characters
print(data[:100])
tokens = enc.encode(data)

# get a data batch
print("##working on one batch.....")
B, T = 4, 32
buf = torch.tensor(tokens[:B*T+1])
buf = buf.to("cuda")
x = buf[:-1].view(B, T)
y = buf[1:].view(B, T)

print(x)
print(y)
# tensor([[ 5962, 22307,    25,   198,  8421,   356,  5120,   597,  2252,    11
        #   340,   307]])

# tensor([[22307,    25,   198,  8421,   356,  5120,   597,  2252,    11,  3285,
        #    307,  1760]])

model = GPT(GPTConfig())
model.to("cuda")

logits = model(x)[0]
print(logits.shape)
# torch.Size([4, 32, 50257])

# cal loss
logits, loss = model(x, y)
print(loss)
# tensor(10.9315, device='cuda:0', grad_fn=<NllLossBackward0>)

# 我们希望初始化的时候，每个token均匀分布，不会过度偏向某一些token，这样初始化不会出现较大的 系统性误差，概率为1/vocab_size
# -log(1/50257) -> 10.8，所谓初始化的概率符合我们预期，初始化的概率大致是保证了均匀分布roughly diffuse


# # grad and back prop
# ## Adam: 随机梯度下降SGD一种优化方案， adamw可以理解为adam的bug-fix版本
# # lr = 3e-4是早期调试的时候的推荐数值
# # 通过对单个batch的overfitting进行验证，看一下是否效果良好
optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
for i in range(50):
    optimizer.zero_grad()
    logits, loss = model(x, y)
    loss.backward() # backward总是执行梯度的+=操作，将梯度累加到现有值上，所以每次迭代需要optimizer.zero_grad()先梯度初始为0
    optimizer.step()
    print(f"step {i}, loss: {loss.item()}")

# step 0, loss: 11.089780807495117
# step 1, loss: 6.618707656860352
# step 2, loss: 4.2506279945373535
# step 3, loss: 2.546597957611084
# step 4, loss: 1.4418233633041382
# step 5, loss: 0.7750691175460815
# step 6, loss: 0.4173423945903778
# step 7, loss: 0.24148188531398773
# step 8, loss: 0.15403734147548676
# step 9, loss: 0.09866859763860703
# step 10, loss: 0.06973658502101898
# step 11, loss: 0.051811542361974716
# ...
# step 45, loss: 0.0030604281928390265
# step 46, loss: 0.002983706770464778
# step 47, loss: 0.0029120517428964376
# step 48, loss: 0.0028447620570659637
# step 49, loss: 0.0027812537737190723

# 下一步，不仅仅拟合一个batch
print("##working on all batches.....")
import tiktoken

class DataLoaderLite:
    def __init__(self, B, T):
        self.B = B
        self.T = T

        with open('input.txt', 'r') as f:
            text = f.read()

        enc = tiktoken.get_encoding('gpt2')
        tokens = enc.encode(text)
        self.tokens = torch.tensor(tokens)
        print(f"loaded {len(self.tokens)} tokens")
        print(f"1 epoch = {len(self.tokens)//(B*T)} batches")

        self.cur_position = 0
    
    def next_batch(self):
        B, T = self.B, self.T
        ## 每次取B*T，以B*T的步长移动
        buf = self.tokens[self.cur_position: self.cur_position+B*T+1]
        x = (buf[:-1]).view(B, T)
        y = (buf[1:]).view(B, T)

        self.cur_position += B*T
        # 如果run out of data数据耗尽，那么从新开始
        if self.cur_position + (B*T+1) > len(self.tokens):
            self.cur_position = 0
        return x, y



train_loader = DataLoaderLite(B = 8, T = 1024) # B 4, T 32 ---> 16, 1024

# float32，计算精度最高，默认方式；
# fp32修改为tf32
torch.set_float32_matmul_precision('high')
# step 49, loss: 5.837480068206787, dt: 680.22, tok/sec: 12043.22

## tf32--->bf16

model = GPT(GPTConfig())
model.to("cuda")
model = torch.compile(model)

import time

# grad and back prop
## Adam: 随机梯度下降SGD一种优化方案， adamw可以理解为adam的bug-fix版本
# lr = 3e-4是早期调试的时候的推荐数值
# 通过对单个batch的overfitting进行验证，看一下是否效果良好
optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
for i in range(50):
    t0 = time.time()

    x, y = train_loader.next_batch()
    x, y = x.to("cuda"), y.to("cuda")
    # 在数据集加载，一般默认在CPU，虽然现在的数据集比较小，GPU完全放得下。但大部分时候数据集很大，为了节省GPU运算显存，一般先加载到CPU，需要时候再传到GPU

    optimizer.zero_grad()
    # bf16--> only for Ampere GPU
    # with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
    #     logits, loss = model(tokens)
    # 先计算loss
    logits, loss = model(x, y)
    loss.backward() # backward总是执行梯度的+=操作，将梯度累加到现有值上，所以每次迭代需要optimizer.zero_grad()先梯度初始为0
    optimizer.step()
    torch.cuda.synchronize()# 等待GPU完成之前已经调度的计算任务

    t1 = time.time()
    dt = (t1-t0)*1000 # time diff in ms
    tokens_per_sec = (train_loader.B*train_loader.T)/(t1-t0)
    print(f"step {i}, loss: {loss.item()}, dt: {dt:.2f}, tok/sec: {tokens_per_sec:.2f}")

# 我们期望的是，我们在获取下一批数据，不会在一个batch过拟合，loss会下降，但是不会下降太多。
# 但是我们仍然预期会下降，因为在50257个token中，很多token没有在input.txt莎士比亚数据集里面出现过，因此在优化中，有一些很容易的优化可以做到，比如一些未出现的数据，对应概率快速推向很小；
# 开始的gain基本就是消除那些从来没有出现的token，在当前的input.txt数据上
# loss也不应该接近0，因为只有50次迭代，还不足以跑完完整的opoch

##working on all batches.....
# loaded 338025 tokens 此处符合gpt2 tokenizer的压缩比，100万个字符，压缩到30万，3:1
# 1 epoch = 2640 batches
# step 0, loss: 11.07473373413086
# step 1, loss: 9.64257526397705
# step 2, loss: 8.623641967773438
# step 3, loss: 9.015697479248047
# step 4, loss: 8.668902397155762
# step 5, loss: 8.18095588684082
# step 6, loss: 8.993752479553223
# step 7, loss: 8.623945236206055
# step 8, loss: 7.9853386878967285
# step 9, loss: 7.889963150024414
# step 10, loss: 8.296610832214355
# step 11, loss: 7.293764114379883
# ...
# step 44, loss: 6.620054244995117
# step 45, loss: 6.677271842956543
# step 46, loss: 5.623128414154053
# step 47, loss: 5.910852432250977
# step 48, loss: 6.777295112609863
# step 49, loss: 6.55256986618042



#         ## weight sharing scheme
        # self.transformer.wte.weight = self.lm_head.weight
# 参考attention is all you need
# 直接把一个参数向量使用两次即可，节省参数，transformer.wte.weight：768*50257是38,597,376，约4million，原始模型是124 million
# 通过权重share，可以节省30%的参数


# 缩放因子补偿
# standard deviation grows inside the residual stream
# torch.randn： normal distribution, 0 mean, 1 std
x = torch.zeros(768)
n = 100 # e.g. 100 layers
for i in range(n):
    x += torch.randn(768) # 没有根据网络深度进行初始化缩放，残差流的激活值的方差会逐渐累计

print(x.std()) 
# tensor(10.1934)


x = torch.zeros(768)
n = 100 # e.g. 100 layers
for i in range(n):
    x += n**-0.5 * torch.randn(768) #使用缩放因子进行补偿，方差维持在1

print(x.std())
# tensor(0.9794)

#模型初始化，gpt2和3论文里面没有太多细节，参考openai代码，初始化时候，wte的std是0.02，wpe的std是0.01


# 计算优化
#大多耗时的操作是矩阵乘法，也就是顶层的分类器，768到50257的映射，还有attn的计算
# 尽量跑满显存
# fp32->tf32->bf16（GPU架构支持）
# torch.compile
