import numpy as np
from scipy.stats import gamma 
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde

""" 
The code provided seems to be part of a sampling algorithm 
that uses the Metropolis-Hastings algorithm to generate samples from a distribution. 
Markov Chain Monte Carlo (MCMC) method for parameter estimation.

Here's a breakdown of what the code does:

    The initial accuracy of the model is evaluated and stored in acc_.
    
    The Dc parameter of the model is perturbed by multiplying it with (1 + 1e-6).
    
    The model is evaluated again with the perturbed Dc value, and the accuracy is stored in acc_dq_.
    
    The accuracy values are extracted and reshaped into a 1D array called acc.
    
    The variance of the noise is computed based on the accuracy values and stored in std2.
    
    The accuracy gradient values are extracted and reshaped into a 1D array called acc_dq.
    
    The covariance matrix X is computed using the difference between acc_dq and acc, divided by the product of Dc and 1e-6.
    
    The inverse of the dot product of X and its transpose is computed and stored in self.Vstart.
    
    Several variables are initialized, including qstart_vect, self.qstart_limits, qparams, Vold, Vnew, SSqprev, and iaccept.
    
    A loop is started for the desired number of samples (self.nsamples).
    
    A new parameter sample q_new is generated by sampling from a normal distribution centered around the last element of qparams using the covariance matrix Vold.
    
    The new sample q_new is checked to see if it falls within the specified limits (self.qstart_limits), and a boolean value accept is set accordingly.
    
    If q_new is accepted, its sum of squares error (SSqnew) is computed using the SSqcalc function.
    
    An acceptance probability is computed based on SSqprev, SSqnew, and std2.
    
    q_new is accepted or rejected based on the acceptance probability and a random number.
    
    If the sample is accepted, it is added to qparams, SSqprev is updated, and iaccept is incremented.
    
    If the sample is rejected, the previous sample is added to qparams.
    
    The estimate of the standard deviation is updated using the aval and bval parameters, and the value is appended to self.std2.
    
    The covariance matrix Vnew is updated every self.adapt_interval samples.
    
    The acceptance ratio is printed.
    
    The self.std2 array is trimmed to exclude burn-in samples (self.nburn).
    
    The accepted samples are returned as qparams[:, self.nburn:].

The acceptreject function checks if a proposed sample falls within the limits 
and decides whether to accept or reject it based on the acceptance probability 
and a random number. It returns a boolean value indicating acceptance 
and the sum of squares error of the accepted or previous proposal.

The SSqcalc function updates the Dc parameter of the model with a proposed value, 
evaluates the model's performance, and computes the sum of squares error 
between the model's accuracy and the data.

"""

class MCMC:
    """
    Class for MCMC sampling
    """
    def __init__(
        self, model, data, qpriors, qstart, nsamples=100, lstm_model={}, adapt_interval=10, verbose=True):

        self.model          = model
        self.qstart         = qstart
        self.qpriors        = qpriors
        self.nsamples       = nsamples # number of samples to take during MCMC algorithm
        self.nburn          = int(nsamples/2) # number of samples to discard during burn-in period
        self.verbose        = verbose
        self.adapt_interval = adapt_interval
        self.data           = data
        self.lstm_model     = lstm_model
        self.n0             = 0.01

        return

    def sample(self):

        # Evaluate the model with the original dc value
        acc_ = self.model.rom_evaluate(self.lstm_model)[1] if self.lstm_model else self.model.evaluate()[1]

        # Perturb the dc value
        self.model.Dc *= (1 + 1e-6)

        # Evaluate the model with the perturbed dc value
        acc_dq_ = self.model.rom_evaluate(self.lstm_model)[1] if self.lstm_model else self.model.evaluate()[1]

        # Extract the values and reshape them to a 1D array
        acc = acc_[:, 0].reshape(1, -1)
        acc_dq = acc_dq_[:, 0].reshape(1, -1)

        # Compute the variance of the noise
        self.std2 = [np.sum((acc - self.data) ** 2, axis=1).item()/(acc.shape[1] - len(self.qpriors))]

        # Compute the covariance matrix
        X                  = ((acc_dq - acc) / (self.model.Dc * 1e-6)).T
        X                  = np.linalg.inv(np.dot(X.T, X))
        self.Vstart        = self.std2[-1] * X 
        qstart_vect        = np.array([[self.qstart]])
        self.qstart_limits = np.array([[self.qpriors[1], self.qpriors[2]]])
        qparams            = np.copy(qstart_vect) # Array of sampled parameters
        Vold               = np.copy(self.Vstart) # Covariance matrix of previously sampled parameters
        Vnew               = np.copy(self.Vstart) # Covariance matrix of current sampled parameters
        SSqprev            = self.SSqcalc(qparams) # Squared error of previously sampled parameters
        iaccept            = 0 # Counter for accepted samples

        for isample in np.arange(self.nsamples):
            # Sample new parameters from a normal distribution with mean being the last element of qparams
            q_new = np.reshape(np.random.multivariate_normal(qparams[:,-1],Vold),(-1,1)) 

            # Accept or reject the new sample based on the Metropolis-Hastings acceptance rule
            accept,SSqnew = self.acceptreject(q_new,SSqprev,self.std2[-1])

            # Print some diagnostic information
            print(isample,accept)
            print("Generated sample ---- ",np.asscalar(q_new))

            # If the new sample is accepted, 
            # add it to the list of sampled parameters
            if accept:
                qparams    = np.concatenate((qparams,q_new),axis=1)
                SSqprev    = SSqnew.copy()
                iaccept    += 1
            else:
                # If the new sample is rejected, 
                # add the previous sample to the list of sampled parameters
                q_new      = np.reshape(qparams[:,-1],(-1,1))
                qparams    = np.concatenate((qparams,q_new),axis=1)

            # Update the estimate of the standard deviation
            aval           = 0.5*(self.n0+self.data.shape[1])
            bval           = 0.5*(self.n0*self.std2[-1]+SSqprev)
            self.std2.append(1/gamma.rvs(aval,scale=1/bval,size=1)[0])

            # Update the covariance matrix if it is time to adapt it
            if (isample+1) % self.adapt_interval == 0:
                try:
                    Vnew = 2.38**2/len(self.qpriors.keys())*np.cov(qparams[:,-self.adapt_interval:])
                    if qparams.shape[0]==1:
                        Vnew = np.reshape(Vnew,(-1,1))
                    Vnew = np.linalg.cholesky(Vnew)
                    Vold = Vnew.copy()
                except:
                    pass

        # Print acceptance ratio
        print("acceptance ratio:",iaccept/self.nsamples)

       # Trim the estimate of the standard deviation to exclude burn-in samples  
        self.std2 = np.asarray(self.std2)[self.nburn:] 
        
        # Return accepted samples
        return qparams[:,self.nburn:]

    def acceptreject(self, q_new, SSqprev, std2):

        # Check if the proposal values are within the limits
        accept = np.all((q_new > self.qstart_limits[:, 0]) & (q_new < self.qstart_limits[:, 1]), axis=0)

        if accept:
            # Compute the sum of squares error of the new proposal
            SSqnew = self.SSqcalc(q_new)

            # Compute the acceptance probability
            accept_prob = np.clip(0.5 * (SSqprev - SSqnew) / std2, -np.inf, 0)

            # Check if the proposal is accepted 
            # based on the acceptance probability and a random number
            accept = accept_prob > np.log(np.random.rand(1))[0]

        if accept:
            # If accepted, return the boolean True and the sum of squares error of the new proposal
            return accept, SSqnew
        else:
            # If rejected, return the boolean False and the sum of squares error of the previous proposal
            return accept, SSqprev

    def SSqcalc(self, q_new):

        # Update the Dc parameter of the model with the new proposal
        self.model.Dc = q_new[0,]

        # Evaluate the model's performance on the problem type and LSTM model
        acc = self.model.rom_evaluate(self.lstm_model)[1] if self.lstm_model else self.model.evaluate()[1]

        # Compute the sum of squares error between the model's accuracy and the data
        SSq = np.sum((acc[:, 0].reshape(1, -1) - self.data)**2, axis=1, keepdims=True)

        return SSq

    def plot_dist(self, qparams, dc):

        # Set up the plot layout with 1 row and 2 columns, 
        # and adjust the width ratios and space between subplots
        n_rows = 1
        n_columns = 2
        gridspec = {'width_ratios': [0.7, 0.15], 'wspace': 0.15}

        # Create the subplots with the specified gridspec
        fig, ax = plt.subplots(n_rows, n_columns, gridspec_kw=gridspec)

        # Set the main plot title with the specified dc value
        fig.suptitle(f'$d_c={dc}\,\mu m$', fontsize=10)

        # Plot the MCMC samples as a blue line in the first subplot
        ax[0].plot(qparams[0, :], 'b-', linewidth=1.0)

        # Get the limits of the y-axis
        ylims = ax[0].get_ylim()

        # Create an array of 1000 evenly spaced points between the y-axis limits
        x = np.linspace(ylims[0], ylims[1], 1000)

        # Calculate the probability density function using Gaussian Kernel Density Estimation
        kde = gaussian_kde(qparams[0, :])

        # Plot the probability density function as a blue line in the second subplot
        ax[1].plot(kde.pdf(x), x, 'b-')

        # Fill the area under the probability density function with a light blue color
        ax[1].fill_betweenx(x, kde.pdf(x), np.zeros(x.shape), alpha=0.3)

        # Set the x-axis limits for the second subplot
        ax[1].set_xlim(0, None)

        # Set labels and axis limits for the first subplot
        ax[0].set_ylabel('$d_c$', fontsize=10)
        ax[0].set_xlim(0, qparams.shape[1])
        ax[0].set_xlabel('Sample number')

        # Set the x-axis label for the second subplot and hide the y-axis
        ax[1].set_xlabel('Prob. density')
        ax[1].get_yaxis().set_visible(False)
        ax[1].get_xaxis().set_visible(True)
        ax[1].get_xaxis().set_ticks([])

        return 