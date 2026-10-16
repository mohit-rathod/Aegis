"""Per-call recurrent state; the ONNX inference session can be shared."""

import numpy as np


class SileroVAD:
    def __init__(self, session):
        self.session = session
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    @classmethod
    def load_session(cls, path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        return ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def probability(self, pcm):
        samples = (
            np.frombuffer(pcm, dtype="<i2").astype(np.float32).reshape(1, -1) / 32768
        )
        if samples.shape != (1, 512):
            raise ValueError("VAD requires 512 samples at 16kHz")
        audio = np.concatenate((self.context, samples), axis=1)
        out, self.state = self.session.run(
            None,
            {
                "input": audio,
                "state": self.state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        self.context = audio[:, -64:]
        return float(out.squeeze())
