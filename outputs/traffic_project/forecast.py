"""Train on independent synthetic days; recursively forecast 10-second counts."""
import numpy as np
import torch
from torch import nn

torch.set_num_threads(1)
L = 12


def demand_rates(t, duration, scenario, day=0):
    # Artificial recurring within-session pattern; not calibrated field demand.
    z = 2 * np.pi * np.asarray(t) / 300
    ns = .18 + .10 * np.sin(z)
    ew = .18 - .10 * np.sin(z)
    r = np.stack([ns, ns, ew, ew], axis=-1)
    if scenario == 'directional_shift':
        r = r + (np.asarray(t) >= duration / 2)[..., None] * np.array([.16, .16, -.07, -.07])
    if scenario == 'heavy':
        r = r * 2.1
    return np.maximum(.015, r * (1 + .05 * np.sin(2 * np.pi * day / 7)))


def features(counts, ends, day):
    tod = 2 * np.pi * (8 * 3600 + np.asarray(ends)) / 86400
    dow = 2 * np.pi * day / 7
    return np.column_stack([np.asarray(counts) / 5, np.sin(tod), np.cos(tod),
                            np.full(len(ends), np.sin(dow)), np.full(len(ends), np.cos(dow))]).astype('float32')


class Transformer(nn.Module):
    def __init__(self):
        super().__init__()
        self.input = nn.Linear(8, 24)
        self.position = nn.Parameter(torch.randn(1, L, 24) * .02)
        layer = nn.TransformerEncoderLayer(24, 4, 48, dropout=0, batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, 1, enable_nested_tensor=False)
        self.output = nn.Sequential(nn.Linear(24, 4), nn.Softplus())

    def forward(self, x):
        return self.output(self.encoder(self.input(x) + self.position)[:, -1]) * 5


def train(config, folder):
    torch.manual_seed(7)
    rng = np.random.default_rng(7)
    xs, ys = [], []
    for day in range(config['training_days']):
        ends = np.arange(10, config['duration_s'] + 1, 10)
        # Per-approach totals (primary/secondary layouts) or the legacy symmetric lane sum.
        scale = np.asarray(config['approach_demand_factors']) if 'approach_demand_factors' in config else sum(config.get('lane_demand_factors', [1.]))
        counts = rng.poisson(demand_rates(ends - 5, config['duration_s'], 'balanced', day) * 10 * scale)
        f = features(counts, ends, day % 7)
        for j in range(L, len(f)):
            xs.append(f[j-L:j]); ys.append(counts[j])
    x, y = torch.tensor(np.array(xs)), torch.tensor(np.array(ys), dtype=torch.float32)
    model = Transformer()
    optimizer = torch.optim.Adam(model.parameters(), lr=.002)
    losses = []
    for epoch in range(config['epochs']):
        order = torch.randperm(len(x))
        loss_sum = 0
        for ids in order.split(128):
            loss = (model(x[ids]) - y[ids]).square().mean()
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            loss_sum += loss.item() * len(ids)
        losses.append(loss_sum / len(x))
    model.eval()
    torch.save(model.state_dict(), folder / 'transformer.pt')
    return model, losses


def predict(model, history, issue, day=2, prior_count=1.8):
    if len(history) < L:
        mean = np.mean(history, axis=0) if history else np.full(4, prior_count)
        return np.tile(mean, (6, 1))
    h = np.array(history[-L:], dtype=float)
    ends = np.arange(issue - 110, issue + 1, 10)
    result = []
    with torch.inference_mode():
        for step in range(6):
            p = model(torch.tensor(features(h, ends, day))[None])[0].numpy()
            result.append(p)
            h = np.vstack([h[1:], p]); ends += 10
    return np.array(result)
