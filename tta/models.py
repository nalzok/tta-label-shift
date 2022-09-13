import jax
import jax.numpy as jnp
from flax import linen as nn

from .resnet import ResNet


class AdaptiveResNet(nn.Module):
    num_layers: int
    C: int
    K: int
    T: float

    def setup(self):
        self.M = self.C * self.K
        self.resnet = ResNet(num_outputs=self.M, num_layers=self.num_layers)
        self.b = self.param('b', jax.nn.initializers.zeros, (self.M,))
        self.source_prior = self.variable('prior', 'source',
                                          jax.nn.initializers.constant(1/self.M,),
                                          None,
                                          (self.M,))
        self.target_prior = self.variable('prior', 'target',
                                          jax.nn.initializers.constant(1/self.M,),
                                          None,
                                          (self.M,))

    def raw_logit(self, x, train: bool):
        logit = self.resnet(x, train)
        logit = logit - jnp.mean(logit, axis=-1, keepdims=True)

        return logit

    def calibrated_logit(self, x, train: bool):
        logit = self.raw_logit(x, train)
        logit = jax.lax.stop_gradient(logit)

        # bias corrected temperature scaling
        logit = logit/self.T + self.b

        return logit

    def adapted_prob(self, x, train: bool):
        logit = self.calibrated_logit(x, train)
        prob = jax.nn.softmax(logit)

        # adaptation
        w = self.target_prior.value / self.source_prior.value
        prob = w * prob
        prob = prob.reshape((-1, self.C, self.K))
        prob = jnp.sum(prob, axis=-1)

        return prob
