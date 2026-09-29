class ConflictError(ValueError):
    def __init__(self, key, batch_index):
        super().__init__(key)
        self.key, self.batch_index = key, batch_index


def target(key):
    raise ConflictError(key, 0)
