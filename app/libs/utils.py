def adapt_parameters(split1: str, split2: str, string: str):
    return [item.split(split1) for item in string.split(split2)]


