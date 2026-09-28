
# 26/09/15 gt: original, commented out

# from artiq.experiment import *
#
# class SetDataset(EnvExperiment):
#     ''' Set the value of a dataset'''
#     def build(self):
#         self.dataGroup = self.get_argument("Dataset group", StringValue(default=''))
#         if self.dataGroup != '':
#             self.dataGroup = str(self.dataGroup) + '.'
#         self.dataName = self.get_argument("Dataset name", StringValue(default=''))
#         self.dataValue = self.get_argument("Dataset value (Float)", NumberValue(default=0, ndecimals=10))
#         self.units = {"s": 1, "ms": 10 ** -3, "us": 10 ** -6, "ns": 10 ** -9, "Hz": 1, "kHz": 10 ** 3, "MHz": 10 ** 6}
#         units_lst = list(self.units.keys())
#         units_lst.append('')
#         self.dataUnit = self.get_argument("Dataset unit", EnumerationValue(units_lst, default=''))
#         self.doPersist = self.get_argument("Persist?", BooleanValue(default=True))
#         self.is_int = self.get_argument("Integer?", BooleanValue(default=False))
#
#         if self.dataUnit not in self.units.keys():
#             self.units[self.dataUnit] = 1
#
#     def run(self):
#         print(self.dataGroup)
#         if self.is_int:
#             self.set_dataset((self.dataGroup + self.dataName), (int(self.dataValue) * self.units[self.dataUnit]), broadcast=True, persist=self.doPersist)
#         else:
#             self.set_dataset((self.dataGroup + self.dataName), (self.dataValue * self.units[self.dataUnit]), broadcast=True, persist=self.doPersist)
#         print("set {} to {}".format(self.dataName,(str(self.dataValue) + " " + self.dataUnit)))

# 26/09/15 gt: updated, to create new list of custom variables under AWG so the precomputer doesnt miss anything

from artiq.experiment import *


class SetDataset(EnvExperiment):
    ''' Set the value of a dataset'''

    def build(self):
        self.dataGroup = self.get_argument("Dataset group", StringValue(default=''))
        if self.dataGroup != '':
            self.dataGroup = str(self.dataGroup) + '.'
        self.dataName = self.get_argument("Dataset name", StringValue(default=''))
        self.dataValue = self.get_argument("Dataset value (Float)", NumberValue(default=0, ndecimals=10))
        self.units = {"s": 1, "ms": 10 ** -3, "us": 10 ** -6, "ns": 10 ** -9, "Hz": 1, "kHz": 10 ** 3, "MHz": 10 ** 6}
        units_lst = list(self.units.keys())
        units_lst.append('')
        self.dataUnit = self.get_argument("Dataset unit", EnumerationValue(units_lst, default=''))
        self.doPersist = self.get_argument("Persist?", BooleanValue(default=True))
        self.is_int = self.get_argument("Integer?", BooleanValue(default=False))

        if self.dataUnit not in self.units.keys():
            self.units[self.dataUnit] = 1

    def run(self):
        full_name = self.dataGroup + self.dataName

        if self.is_int:
            self.set_dataset(full_name, (int(self.dataValue) * self.units[self.dataUnit]), broadcast=True,
                             persist=self.doPersist)
        else:
            self.set_dataset(full_name, (self.dataValue * self.units[self.dataUnit]), broadcast=True,
                             persist=self.doPersist)
        print(f"set {self.dataName} to {self.dataValue} {self.dataUnit}")

        # --- NEW REGISTRY LOGIC ---
        # If this is an AWG variable, add it to our global custom registry!
        if full_name.startswith("AWG.ch"):
            try:
                registry = self.get_dataset("AWG.Custom_Variables")
            except Exception:
                registry = []  # Create it if it doesn't exist yet

            if full_name not in registry:
                registry.append(full_name)
                self.set_dataset("AWG.Custom_Variables", registry, broadcast=True, persist=True)
                print(f"[+] Added '{full_name}' to AWG dynamic discovery registry.")
