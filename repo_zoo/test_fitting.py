#import logging
import ndscan.experiment as nd


#logger = logging.getLogger(__name__)


class BaseExp(nd.ExpFragment):
    def build_fragment(self):
        self.setattr_param("param", nd.FloatParam, "a parameter", 0)
        self.setattr_result("result", nd.FloatChannel)

    def run_once(self):
        self.result.push(0)

    def get_default_analyses(self):
        def _analysis_fun(axis_values, result_values, analysis_results):
            logger.info(f"{'_'.join(self._fragment_path)} analysis...")
            analysis_results['fit_result'].push(axis_values[self.param][0])

        return [
            nd.OnlineFit("line", data={"x": self.param, "y": self.result}),
            nd.CustomAnalysis(
                [self.param],
                _analysis_fun,
                [nd.FloatChannel("fit_result")]
            )
        ]

class ParentExp(nd.ExpFragment):
    def build_fragment(self):
        self.base_exps = [self.setattr_fragment(f"base{i}", BaseExp) for i in range(3)]
        self.setattr_param_rebind('param',
            self.base_exps[0].param,
            [exp.param for exp in self.base_exps[1:]],
            description="a parent param"
        )

    def run_once(self):
        for base_exp in self.base_exps:
            base_exp.run_once()


class SubscanExp(nd.ExpFragment):
    def build_fragment(self):
        self.setattr_fragment('parent', ParentExp)
        nd.setattr_subscan(
            self,
            "scan",
            self.parent,
            [(self.parent, "param")],
            expose_analysis_results=True,
        )

    def run_once(self):
        scan_params = nd.LinearGenerator(-1, 1, 5, True)
        _, _, results = self.scan.run([(self.parent.param, scan_params)])

ScanBaseExp = nd.make_fragment_scan_exp(BaseExp)
ScanParentExp = nd.make_fragment_scan_exp(ParentExp)
ScanScanExp = nd.make_fragment_scan_exp(SubscanExp)
