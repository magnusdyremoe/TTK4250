# %% imports
import scipy
import scipy.io
import scipy.stats
from typing import List

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

import dynamicmodels
import measurementmodels
import ekf
import imm
import pda
from gaussparams import GaussParams
import estimationstatistics as estats
from mixturedata import MixtureParameters

# %% plot config check and style setup


# to see your plot config
print(f"matplotlib backend: {matplotlib.get_backend()}")
print(f"matplotlib config file: {matplotlib.matplotlib_fname()}")
print(f"matplotlib config dir: {matplotlib.get_configdir()}")
plt.close("all")

# try to set separate window ploting
if "inline" in matplotlib.get_backend():
    print("Plotting is set to inline at the moment:", end=" ")

    if "ipykernel" in matplotlib.get_backend():
        print("backend is ipykernel (IPython?)")
        print("Trying to set backend to separate window:", end=" ")
        import IPython

        IPython.get_ipython().run_line_magic("matplotlib", "")
    else:
        print("unknown inline backend")

print("continuing with this plotting backend", end="\n\n\n")


# set styles
try:
    # installed with "pip install SciencePLots" (https://github.com/garrettj403/SciencePlots.git)
    # gives quite nice plots
    plt_styles = ["science", "grid", "bright", "no-latex"]
    plt.style.use(plt_styles)
    print(f"pyplot using style set {plt_styles}")
except Exception as e:
    print(e)
    print("setting grid and only grid and legend manually")
    plt.rcParams.update(
        {
            # setgrid
            "axes.grid": True,
            "grid.linestyle": ":",
            "grid.color": "k",
            "grid.alpha": 0.5,
            "grid.linewidth": 0.5,
            # Legend
            "legend.frameon": True,
            "legend.framealpha": 1.0,
            "legend.fancybox": True,
            "legend.numpoints": 1,
        }
    )


# %% load data and plot
filename_to_load = "data_joyride.mat"
loaded_data = scipy.io.loadmat(filename_to_load)
K = loaded_data["K"].item()
Ts = loaded_data["Ts"].squeeze()
Tmean = np.mean(Ts)
Xgt = loaded_data["Xgt"].T
Z = [zk.T for zk in loaded_data["Z"].ravel()]


# plot measurements close to the trajectory

# plot measurements close to the trajectory
fig1, ax1 = plt.subplots(num=1, clear=True)

Z_plot_data = np.empty((0, 2), dtype=float)
plot_measurement_distance = 45
for Zk, xgtk in zip(Z, Xgt):
    to_plot = np.linalg.norm(Zk - xgtk[None:2], axis=1) <= plot_measurement_distance
    Z_plot_data = np.append(Z_plot_data, Zk[to_plot], axis=0)

ax1.scatter(*Z_plot_data.T, color="C1")
ax1.plot(*Xgt.T[:2], color="C0", linewidth=1.5)
ax1.set_title("True trajectory and the nearby measurements")
plt.show(block=False)

# %% play measurement movie. Remember that you can cross out the window
play_movie = False
play_slice = slice(0, K)
if play_movie:
    if "inline" in matplotlib.get_backend():
        print("the movie might not play with inline plots")
    fig2, ax2 = plt.subplots(num=2, clear=True)
    sh = ax2.scatter(np.nan, np.nan)
    th = ax2.set_title(f"measurements at step 0")
    mins = np.vstack(Z).min(axis=0)
    maxes = np.vstack(Z).max(axis=0)
    ax2.axis([mins[0], maxes[0], mins[1], maxes[1]])
    plotpause = 0.1
    # sets a pause in between time steps if it goes to fast
    for k, Zk in enumerate(Z[play_slice]):
        sh.set_offsets(Zk)
        th.set_text(f"measurements at step {k}")
        fig2.canvas.draw_idle()
        plt.show(block=False)
        plt.pause(plotpause)
    plt.show()
# %% setup and track

#Essentially copying run_imm_pda.py and adjusting time which is the only real difference to make the code run

# sensor

sigma_z = 15
clutter_intensity = 1e-4

PD = 0.9
gate_size = 5

# dynamic models

sigma_a_CV = 0.9

sigma_a_CT = 1.3
sigma_omega = 0.04


#Without CV High

# markov chain
PI11 = 0.9
PI22 = 0.9

p10 = 0.9  # initvalue for mode probabilities

PI = np.array([[PI11, (1 - PI11)], [(1 - PI22), PI22]])

assert np.allclose(np.sum(PI, axis=1), 1), "rows of PI must sum to 1"


mean_init = Xgt[0]
mean_init = np.append(mean_init,0.1)
cov_init = np.diag([30, 30, 1, 1, 0.5]) ** 2  # THIS WILL NOT BE GOOD


mode_probabilities_init = np.array([p10,(1-p10)])
mode_states_init = GaussParams(mean_init, cov_init)
init_imm_state = MixtureParameters(mode_probabilities_init, [mode_states_init] * 2)

assert np.allclose(
    np.sum(mode_probabilities_init), 1
), "initial mode probabilities must sum to 1"

# make model
measurement_model = measurementmodels.CartesianPosition(sigma_z, state_dim=5)
dynamic_models: List[dynamicmodels.DynamicModel] = []
dynamic_models.append(dynamicmodels.WhitenoiseAccelleration(sigma_a_CV, n=5))
#dynamic_models.append(dynamicmodels.WhitenoiseAccelleration(sigma_a_CV_high, n=5))
dynamic_models.append(dynamicmodels.ConstantTurnrate(sigma_a_CT, sigma_omega))
ekf_filters = []
ekf_filters.append(ekf.EKF(dynamic_models[0], measurement_model))
ekf_filters.append(ekf.EKF(dynamic_models[1], measurement_model))
#ekf_filters.append(ekf.EKF(dynamic_models[2], measurement_model))
imm_filter = imm.IMM(ekf_filters, PI)

tracker = pda.PDA(imm_filter, clutter_intensity, PD, gate_size)

#init_imm_pda_state = tracker.init_filter_state(init__immstate)


NEES = np.zeros(K)
NEESpos = np.zeros(K)
NEESvel = np.zeros(K)

tracker_update = init_imm_state
tracker_update_list = []
tracker_predict_list = []
tracker_estimate_list = []

Taccumulated = 0.0


print(tracker_estimate_list)
# estimate
for k, (Zk, x_true_k) in enumerate(zip(Z, Xgt)):
    
    tracker_predict = tracker.predict(tracker_update,Ts[k-1])
    tracker_update = tracker.update(Zk, tracker_predict)

    # You can look at the prediction estimate as well
    tracker_estimate = tracker.estimate(tracker_update)

    NEES[k] = estats.NEES(*tracker_estimate, x_true_k, idxs=np.arange(4))
    NEESpos[k] = estats.NEES(*tracker_estimate, x_true_k, idxs=np.arange(2))
    NEESvel[k] = estats.NEES(*tracker_estimate, x_true_k, idxs=np.arange(2, 4))

    tracker_predict_list.append(tracker_predict)
    tracker_update_list.append(tracker_update)
    tracker_estimate_list.append(tracker_estimate)


x_hat = np.array([est.mean for est in tracker_estimate_list])
prob_hat = np.array([upd.weights for upd in tracker_update_list])

# calculate a performance metrics
poserr = np.linalg.norm(x_hat[:, :2] - Xgt[:, :2], axis=1)
velerr = np.linalg.norm(x_hat[:, 2:4] - Xgt[:, 2:4], axis=1)
posRMSE = np.sqrt(
    np.mean(poserr ** 2)
)  # not true RMSE (which is over monte carlo simulations)
velRMSE = np.sqrt(np.mean(velerr ** 2))
# not true RMSE (which is over monte carlo simulations)
peak_pos_deviation = poserr.max()
peak_vel_deviation = velerr.max()


# consistency
confprob = 0.9
CI2 = np.array(scipy.stats.chi2.interval(confprob, 2))
CI4 = np.array(scipy.stats.chi2.interval(confprob, 4))

confprob = confprob
CI2K = np.array(scipy.stats.chi2.interval(confprob, 2 * K)) / K
CI4K = np.array(scipy.stats.chi2.interval(confprob, 4 * K)) / K
ANEESpos = np.mean(NEESpos)
ANEESvel = np.mean(NEESvel)
ANEES = np.mean(NEES)

# %% plots
# trajectory
fig3, axs3 = plt.subplots(1, 2, num=3, clear=True)
axs3[0].plot(*x_hat.T[:2], label=r"$\hat x$")
axs3[0].plot(*Xgt.T[:2], label="$x$")
axs3[0].set_title(
    f"RMSE(pos, vel) = ({posRMSE:.3f}, {velRMSE:.3f})\npeak_dev(pos, vel) = ({peak_pos_deviation:.3f}, {peak_vel_deviation:.3f})"
)
axs3[0].axis("equal")
# probabilities
axs3[1].plot(np.arange(K) * Tmean, prob_hat)
axs3[1].set_ylim([0, 1])
axs3[1].set_ylabel("mode probability")
axs3[1].set_xlabel("time")

# NEES
fig4, axs4 = plt.subplots(3, sharex=True, num=4, clear=True)
axs4[0].plot(np.arange(K) * Tmean, NEESpos)
axs4[0].plot([0, (K - 1) * Tmean], np.repeat(CI2[None], 2, 0), "--r")
axs4[0].set_ylabel("NEES pos")
inCIpos = np.mean((CI2[0] <= NEESpos) * (NEESpos <= CI2[1]))
axs4[0].set_title(f"{inCIpos*100:.1f}% inside {confprob*100:.1f}% CI")

axs4[1].plot(np.arange(K) * Tmean, NEESvel)
axs4[1].plot([0, (K - 1) * Tmean], np.repeat(CI2[None], 2, 0), "--r")
axs4[1].set_ylabel("NEES vel")
inCIvel = np.mean((CI2[0] <= NEESvel) * (NEESvel <= CI2[1]))
axs4[1].set_title(f"{inCIvel*100:.1f}% inside {confprob*100:.1f}% CI")

axs4[2].plot(np.arange(K) * Tmean, NEES)
axs4[2].plot([0, (K - 1) * Tmean], np.repeat(CI4[None], 2, 0), "--r")
axs4[2].set_ylabel("NEES")
inCI = np.mean((CI2[0] <= NEES) * (NEES <= CI2[1]))
axs4[2].set_title(f"{inCI*100:.1f}% inside {confprob*100:.1f}% CI")

print(f"ANEESpos = {ANEESpos:.2f} with CI = [{CI2K[0]:.2f}, {CI2K[1]:.2f}]")
print(f"ANEESvel = {ANEESvel:.2f} with CI = [{CI2K[0]:.2f}, {CI2K[1]:.2f}]")
print(f"ANEES = {ANEES:.2f} with CI = [{CI4K[0]:.2f}, {CI4K[1]:.2f}]")

# errors
fig5, axs5 = plt.subplots(2, num=5, clear=True)
axs5[0].plot(np.arange(K) * Tmean, np.linalg.norm(x_hat[:, :2] - Xgt[:, :2], axis=1))
axs5[0].set_ylabel("position error")

axs5[1].plot(np.arange(K) * Tmean, np.linalg.norm(x_hat[:, 2:4] - Xgt[:, 2:4], axis=1))
axs5[1].set_ylabel("velocity error")

plt.show()